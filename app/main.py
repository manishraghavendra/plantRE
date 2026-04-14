from __future__ import annotations

import csv
import io
import json
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session, joinedload

from app.cms import router as cms_router
from app.database import SessionLocal, init_db
from app.models import (
    Citation,
    EnvironmentCondition,
    GrowingMedium,
    GrowingProfile,
    Plant,
    Source,
)
from app.schemas import GrowingProfileCreate
from app.search_logic import global_search
from app.seed_loader import run_seed

templates = Jinja2Templates(directory=str(Path(__file__).resolve().parent / "templates"))
_STATIC = Path(__file__).resolve().parent / "static"


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_db()
    with SessionLocal() as db:
        if db.scalar(select(func.count()).select_from(Plant)) == 0:
            run_seed()
    yield


app = FastAPI(title="Extreme-conditions plant database", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=str(_STATIC)), name="static")
app.include_router(cms_router)


@app.post("/api/seed")
def api_seed():
    """Reload taxonomy and demo profiles from JSON (destructive clear)."""
    run_seed()
    return {"status": "ok", "message": "Database seeded from JSON files."}


@app.get("/plants", tags=["read"])
def list_plants(
    db: Session = Depends(get_db),
    environment_code: str | None = None,
    medium_name: str | None = None,
    edible_part: str | None = None,
    confidence_level: str | None = None,
):
    stmt = select(Plant).order_by(Plant.scientific_name)
    if environment_code or medium_name or confidence_level:
        stmt = stmt.join(GrowingProfile)
        if environment_code:
            stmt = stmt.join(
                EnvironmentCondition,
                GrowingProfile.environment_condition_id == EnvironmentCondition.id,
            ).where(EnvironmentCondition.code == environment_code)
        if medium_name:
            stmt = stmt.join(GrowingMedium, GrowingProfile.medium_id == GrowingMedium.id).where(
                GrowingMedium.name == medium_name
            )
        if confidence_level:
            stmt = stmt.where(GrowingProfile.confidence_level == confidence_level)
        stmt = stmt.distinct()
    plants = list(db.scalars(stmt).unique().all())
    if edible_part:
        plants = [
            p for p in plants if edible_part in (json.loads(p.edible_parts) if p.edible_parts else [])
        ]
    return [
        {
            "id": p.id,
            "scientific_name": p.scientific_name,
            "common_names": json.loads(p.common_names) if p.common_names else [],
            "life_cycle": p.life_cycle,
            "edible_parts": json.loads(p.edible_parts) if p.edible_parts else [],
            "image_url": p.image_url,
        }
        for p in plants
    ]


@app.get("/plants/{plant_id}", tags=["read"])
def get_plant(plant_id: int, db: Session = Depends(get_db)):
    p = db.get(Plant, plant_id)
    if not p:
        raise HTTPException(status_code=404, detail="Plant not found")
    profiles = (
        db.scalars(
            select(GrowingProfile)
            .where(GrowingProfile.plant_id == plant_id)
            .options(
                joinedload(GrowingProfile.steps),
                joinedload(GrowingProfile.requirements),
            )
        )
        .unique()
        .all()
    )
    env_ids = {pr.environment_condition_id for pr in profiles}
    med_ids = {pr.medium_id for pr in profiles}
    envs = {}
    meds = {}
    if env_ids:
        envs = {
            e.id: e
            for e in db.scalars(select(EnvironmentCondition).where(EnvironmentCondition.id.in_(env_ids))).all()
        }
    if med_ids:
        meds = {
            m.id: m for m in db.scalars(select(GrowingMedium).where(GrowingMedium.id.in_(med_ids))).all()
        }
    out_profiles = []
    for pr in profiles:
        cite_rows = db.execute(
            select(Citation, Source)
            .join(Source, Citation.source_id == Source.id)
            .where(Citation.target_type == "profile", Citation.target_id == pr.id)
        ).all()
        citations = [
            {"source_title": s.title, "url": s.url, "source_type": s.source_type, "quote": c.quote, "page": c.page}
            for c, s in cite_rows
        ]
        hz_rows = db.execute(
            text(
                "SELECT h.name, h.kind, g.mitigation_detail, g.evidence_notes "
                "FROM growing_profile_hazard g JOIN hazard h ON h.id = g.hazard_id "
                "WHERE g.growing_profile_id = :pid ORDER BY h.kind, h.name"
            ),
            {"pid": pr.id},
        ).all()
        profile_hazards = [
            {"name": r[0], "kind": r[1], "mitigation_detail": r[2], "evidence_notes": r[3]} for r in hz_rows
        ]
        out_profiles.append(
            {
                "id": pr.id,
                "environment": {
                    "code": envs[pr.environment_condition_id].code,
                    "name": envs[pr.environment_condition_id].name,
                    "is_speculative": bool(envs[pr.environment_condition_id].is_speculative),
                },
                "medium": meds[pr.medium_id].name,
                "summary": pr.summary,
                "difficulty": pr.difficulty,
                "confidence_level": pr.confidence_level,
                "hardiness_zone_min": pr.hardiness_zone_min,
                "hardiness_zone_max": pr.hardiness_zone_max,
                "climate_context": pr.climate_context,
                "steps": [
                    {"step_order": s.step_order, "title": s.title, "body": s.body, "equipment": s.equipment}
                    for s in sorted(pr.steps, key=lambda x: x.step_order)
                ],
                "requirements": [
                    {
                        "category": r.category,
                        "value_min": r.value_min,
                        "value_max": r.value_max,
                        "unit": r.unit,
                        "notes": r.notes,
                    }
                    for r in pr.requirements
                ],
                "hazards": profile_hazards,
                "citations": citations,
            }
        )
    return {
        "id": p.id,
        "scientific_name": p.scientific_name,
        "common_names": json.loads(p.common_names) if p.common_names else [],
        "life_cycle": p.life_cycle,
        "native_regions": p.native_regions,
        "edible_parts": json.loads(p.edible_parts) if p.edible_parts else [],
        "toxicity_notes": p.toxicity_notes,
        "image_url": p.image_url,
        "growing_profiles": out_profiles,
    }


@app.get("/plants/{plant_id}/profiles", tags=["read"])
def list_profiles_for_plant(
    plant_id: int,
    db: Session = Depends(get_db),
    environment: str | None = None,
):
    if not db.get(Plant, plant_id):
        raise HTTPException(status_code=404, detail="Plant not found")
    stmt = select(GrowingProfile).where(GrowingProfile.plant_id == plant_id)
    if environment:
        stmt = stmt.join(EnvironmentCondition).where(EnvironmentCondition.code == environment)
    profiles = db.scalars(stmt).all()
    return [{"id": pr.id, "summary": pr.summary, "confidence_level": pr.confidence_level} for pr in profiles]


@app.get("/export/profiles.csv")
def export_profiles_csv(db: Session = Depends(get_db)):
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(
        [
            "profile_id",
            "plant_scientific_name",
            "environment_code",
            "medium_name",
            "difficulty",
            "confidence_level",
            "summary",
            "climate_context",
        ]
    )
    rows = db.execute(
        select(
            GrowingProfile.id,
            Plant.scientific_name,
            EnvironmentCondition.code,
            GrowingMedium.name,
            GrowingProfile.difficulty,
            GrowingProfile.confidence_level,
            GrowingProfile.summary,
            GrowingProfile.climate_context,
        )
        .join(Plant, GrowingProfile.plant_id == Plant.id)
        .join(EnvironmentCondition, GrowingProfile.environment_condition_id == EnvironmentCondition.id)
        .join(GrowingMedium, GrowingProfile.medium_id == GrowingMedium.id)
        .order_by(Plant.scientific_name, EnvironmentCondition.code)
    ).all()
    for r in rows:
        w.writerow(list(r))
    buf.seek(0)
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=growing_profiles.csv"},
    )


@app.post("/api/growing-profiles", tags=["write"])
def create_growing_profile(body: GrowingProfileCreate, db: Session = Depends(get_db)):
    if not db.get(Plant, body.plant_id):
        raise HTTPException(404, "plant_id not found")
    if not db.get(EnvironmentCondition, body.environment_condition_id):
        raise HTTPException(404, "environment_condition_id not found")
    if not db.get(GrowingMedium, body.medium_id):
        raise HTTPException(404, "medium_id not found")
    for sid in body.citation_source_ids:
        if not db.get(Source, sid):
            raise HTTPException(404, f"source id {sid} not found")

    gp = GrowingProfile(
        plant_id=body.plant_id,
        environment_condition_id=body.environment_condition_id,
        medium_id=body.medium_id,
        hardiness_zone_min=body.hardiness_zone_min,
        hardiness_zone_max=body.hardiness_zone_max,
        summary=body.summary,
        climate_context=body.climate_context,
        difficulty=body.difficulty,
        confidence_level=body.confidence_level,
        last_reviewed_at=body.last_reviewed_at,
    )
    db.add(gp)
    try:
        db.flush()
    except Exception as e:
        db.rollback()
        raise HTTPException(409, f"Unique constraint or DB error: {e}") from e

    for sid in body.citation_source_ids:
        db.add(Citation(source_id=sid, target_type="profile", target_id=gp.id))
    db.commit()
    db.refresh(gp)
    return {"id": gp.id, "plant_id": gp.plant_id, "environment_condition_id": gp.environment_condition_id}


@app.get("/", response_class=HTMLResponse)
def ui_home(request: Request, db: Session = Depends(get_db)):
    plants = db.scalars(select(Plant).order_by(Plant.scientific_name)).all()
    items = [
        {
            "id": p.id,
            "scientific_name": p.scientific_name,
            "common_names": json.loads(p.common_names) if p.common_names else [],
            "image_url": p.image_url,
        }
        for p in plants
    ]
    return templates.TemplateResponse(
        "index.html",
        {"request": request, "plants": items, "title": "Plants", "query": ""},
    )


@app.get("/about", response_class=HTMLResponse)
def ui_about(request: Request):
    return templates.TemplateResponse(
        "about.html",
        {"request": request, "title": "About", "query": ""},
    )


@app.get("/search", response_class=HTMLResponse)
def ui_search(request: Request, q: str = "", db: Session = Depends(get_db)):
    raw = (q or "").strip()
    message = None
    results = None
    if raw and len(raw) < 2:
        message = "Type at least 2 characters."
    elif raw:
        results = global_search(db, raw)
    return templates.TemplateResponse(
        "search.html",
        {
            "request": request,
            "title": "Search",
            "query": q or "",
            "results": results,
            "message": message,
        },
    )


@app.get("/api/search", tags=["read"])
def api_search(q: str = "", db: Session = Depends(get_db)):
    return global_search(db, q)


@app.get("/plant/{plant_id}", response_class=HTMLResponse)
def ui_plant(request: Request, plant_id: int, db: Session = Depends(get_db)):
    data = get_plant(plant_id, db)
    return templates.TemplateResponse(
        "plant.html",
        {"request": request, "plant": data, "title": data["scientific_name"], "query": ""},
    )
