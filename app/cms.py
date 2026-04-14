"""Browser-based CMS for plants, profiles, steps, requirements, hazards, citations, and sources."""

from __future__ import annotations

import json
from pathlib import Path
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import delete, func, select, text
from sqlalchemy.orm import Session, joinedload

from app.database import SessionLocal
from app.plant_images import clear_uploaded_images, save_plant_upload
from app.models import (
    Citation,
    EnvironmentCondition,
    GrowingMedium,
    GrowingProfile,
    GrowingStep,
    Hazard,
    Plant,
    PlantType,
    Requirement,
    Source,
)

templates = Jinja2Templates(directory=str(Path(__file__).resolve().parent / "templates"))

router = APIRouter(prefix="/admin", tags=["admin"])

LIFE_CYCLES = ["annual", "perennial", "biennial"]
DIFFICULTIES = ["beginner", "intermediate", "advanced"]
CONFIDENCE_LEVELS = ["peer_reviewed", "field_practice", "speculative"]
SOURCE_TYPES = ["peer_review", "extension", "grey_literature", "community"]
REQ_CATEGORIES = ["light", "water", "temp", "soil_ph", "nutrients", "spacing", "harvest"]


def _apply_plant_image_fields(
    p: Plant,
    image_url_input: str,
    file: UploadFile | None,
    clear_image: str | None,
) -> None:
    if clear_image in ("on", "true", "1", "yes"):
        p.image_url = None
        clear_uploaded_images(p.id)
        return
    if file is not None and file.filename:
        saved = save_plant_upload(p.id, file)
        if saved:
            p.image_url = saved
            return
    raw = (image_url_input or "").strip()
    p.image_url = raw or None


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _comma_list(s: str | None) -> list[str]:
    if not s or not str(s).strip():
        return []
    return [x.strip() for x in str(s).split(",") if x.strip()]


def _delete_profile_cascade(db: Session, profile_id: int) -> None:
    step_ids = list(db.scalars(select(GrowingStep.id).where(GrowingStep.growing_profile_id == profile_id)))
    if step_ids:
        db.execute(delete(Citation).where(Citation.target_type == "step", Citation.target_id.in_(step_ids)))
    db.execute(delete(Citation).where(Citation.target_type == "profile", Citation.target_id == profile_id))
    db.execute(delete(GrowingStep).where(GrowingStep.growing_profile_id == profile_id))
    db.execute(delete(Requirement).where(Requirement.growing_profile_id == profile_id))
    db.execute(
        text("DELETE FROM growing_profile_hazard WHERE growing_profile_id = :pid"),
        {"pid": profile_id},
    )
    db.execute(delete(GrowingProfile).where(GrowingProfile.id == profile_id))


def _sync_profile_citations(db: Session, profile_id: int, source_ids: list[int]) -> None:
    db.execute(delete(Citation).where(Citation.target_type == "profile", Citation.target_id == profile_id))
    for sid in source_ids:
        db.add(Citation(source_id=sid, target_type="profile", target_id=profile_id))


def _assert_profile_citations(db: Session, profile_id: int, confidence_level: str) -> None:
    if confidence_level == "speculative":
        return
    n = db.scalar(
        select(Citation.id)
        .where(Citation.target_type == "profile", Citation.target_id == profile_id)
        .limit(1)
    )
    if n is None:
        raise ValueError("Non-speculative profiles need at least one citation (pick one or more sources).")


@router.get("/", response_class=HTMLResponse)
def admin_home(request: Request):
    return templates.TemplateResponse(
        "admin/dashboard.html",
        {"request": request, "title": "Admin"},
    )


# --- Sources ---
@router.get("/sources", response_class=HTMLResponse)
def admin_sources_list(request: Request, db: Session = Depends(get_db)):
    sources = db.scalars(select(Source).order_by(Source.title)).all()
    return templates.TemplateResponse(
        "admin/sources_list.html",
        {"request": request, "sources": sources, "title": "Sources"},
    )


@router.get("/sources/new", response_class=HTMLResponse)
def admin_source_new_form(request: Request):
    return templates.TemplateResponse(
        "admin/source_form.html",
        {
            "request": request,
            "title": "New source",
            "source": None,
            "source_types": SOURCE_TYPES,
            "error": request.query_params.get("error"),
        },
    )


@router.post("/sources/new")
def admin_source_new(
    request: Request,
    db: Session = Depends(get_db),
    title: str = Form(...),
    url: str | None = Form(None),
    publisher: str | None = Form(None),
    year: str | None = Form(None),
    source_type: str = Form(...),
):
    if source_type not in SOURCE_TYPES:
        return RedirectResponse(
            url="/admin/sources/new?error=" + quote("Invalid source type"),
            status_code=303,
        )
    y = int(year) if year and str(year).strip().isdigit() else None
    s = Source(title=title.strip(), url=url.strip() or None, publisher=publisher.strip() or None, year=y, source_type=source_type)
    db.add(s)
    db.commit()
    return RedirectResponse(url="/admin/sources", status_code=303)


@router.get("/sources/{source_id}/edit", response_class=HTMLResponse)
def admin_source_edit_form(request: Request, source_id: int, db: Session = Depends(get_db)):
    s = db.get(Source, source_id)
    if not s:
        raise HTTPException(404)
    return templates.TemplateResponse(
        "admin/source_form.html",
        {
            "request": request,
            "title": "Edit source",
            "source": s,
            "source_types": SOURCE_TYPES,
            "error": request.query_params.get("error"),
        },
    )


@router.post("/sources/{source_id}/edit")
def admin_source_edit(
    source_id: int,
    db: Session = Depends(get_db),
    title: str = Form(...),
    url: str | None = Form(None),
    publisher: str | None = Form(None),
    year: str | None = Form(None),
    source_type: str = Form(...),
):
    s = db.get(Source, source_id)
    if not s:
        raise HTTPException(404)
    if source_type not in SOURCE_TYPES:
        return RedirectResponse(
            url=f"/admin/sources/{source_id}/edit?error=" + quote("Invalid source type"),
            status_code=303,
        )
    y = int(year) if year and str(year).strip().isdigit() else None
    s.title = title.strip()
    s.url = url.strip() or None
    s.publisher = publisher.strip() or None
    s.year = y
    s.source_type = source_type
    db.commit()
    return RedirectResponse(url="/admin/sources", status_code=303)


@router.post("/sources/{source_id}/delete")
def admin_source_delete(source_id: int, db: Session = Depends(get_db)):
    s = db.get(Source, source_id)
    if not s:
        raise HTTPException(404)
    db.delete(s)
    db.commit()
    return RedirectResponse(url="/admin/sources", status_code=303)


# --- Plants ---
@router.get("/plants", response_class=HTMLResponse)
def admin_plants_list(request: Request, db: Session = Depends(get_db)):
    plants = db.scalars(select(Plant).options(joinedload(Plant.plant_type)).order_by(Plant.scientific_name)).all()
    return templates.TemplateResponse(
        "admin/plants_list.html",
        {"request": request, "plants": plants, "title": "Plants (admin)"},
    )


@router.get("/plants/new", response_class=HTMLResponse)
def admin_plant_new_form(request: Request, db: Session = Depends(get_db)):
    types = db.scalars(select(PlantType).order_by(PlantType.name)).all()
    return templates.TemplateResponse(
        "admin/plant_form.html",
        {
            "request": request,
            "title": "New plant",
            "plant": None,
            "plant_types": types,
            "life_cycles": LIFE_CYCLES,
            "common_names_csv": "",
            "edible_parts_csv": "",
            "error": request.query_params.get("error"),
        },
    )


@router.post("/plants/new")
def admin_plant_new(
    db: Session = Depends(get_db),
    scientific_name: str = Form(...),
    plant_type_id: int = Form(...),
    life_cycle: str = Form(...),
    common_names: str = Form(""),
    edible_parts: str = Form(""),
    native_regions: str = Form(""),
    toxicity_notes: str = Form(""),
    image_url: str = Form(""),
    image_file: UploadFile | None = File(None),
):
    if life_cycle not in LIFE_CYCLES:
        return RedirectResponse(url="/admin/plants/new?error=" + quote("Invalid life cycle"), status_code=303)
    if not db.get(PlantType, plant_type_id):
        return RedirectResponse(url="/admin/plants/new?error=" + quote("Invalid plant type"), status_code=303)
    p = Plant(
        scientific_name=scientific_name.strip(),
        common_names=json.dumps(_comma_list(common_names)),
        plant_type_id=plant_type_id,
        life_cycle=life_cycle,
        native_regions=native_regions.strip() or None,
        edible_parts=json.dumps(_comma_list(edible_parts)),
        toxicity_notes=toxicity_notes.strip() or None,
    )
    db.add(p)
    try:
        db.flush()
        _apply_plant_image_fields(p, image_url, image_file, None)
        db.commit()
    except Exception as e:
        db.rollback()
        return RedirectResponse(url="/admin/plants/new?error=" + quote(str(e)), status_code=303)
    return RedirectResponse(url=f"/admin/plants/{p.id}/profiles", status_code=303)


@router.get("/plants/{plant_id}/edit", response_class=HTMLResponse)
def admin_plant_edit_form(request: Request, plant_id: int, db: Session = Depends(get_db)):
    p = db.get(Plant, plant_id)
    if not p:
        raise HTTPException(404)
    types = db.scalars(select(PlantType).order_by(PlantType.name)).all()
    return templates.TemplateResponse(
        "admin/plant_form.html",
        {
            "request": request,
            "title": "Edit plant",
            "plant": p,
            "plant_types": types,
            "life_cycles": LIFE_CYCLES,
            "common_names_csv": ", ".join(json.loads(p.common_names) if p.common_names else []),
            "edible_parts_csv": ", ".join(json.loads(p.edible_parts) if p.edible_parts else []),
            "error": request.query_params.get("error"),
        },
    )


@router.post("/plants/{plant_id}/edit")
def admin_plant_edit(
    plant_id: int,
    db: Session = Depends(get_db),
    scientific_name: str = Form(...),
    plant_type_id: int = Form(...),
    life_cycle: str = Form(...),
    common_names: str = Form(""),
    edible_parts: str = Form(""),
    native_regions: str = Form(""),
    toxicity_notes: str = Form(""),
    image_url: str = Form(""),
    image_file: UploadFile | None = File(None),
    clear_image: str | None = Form(None),
):
    p = db.get(Plant, plant_id)
    if not p:
        raise HTTPException(404)
    if life_cycle not in LIFE_CYCLES:
        return RedirectResponse(
            url=f"/admin/plants/{plant_id}/edit?error=" + quote("Invalid life cycle"),
            status_code=303,
        )
    if not db.get(PlantType, plant_type_id):
        return RedirectResponse(
            url=f"/admin/plants/{plant_id}/edit?error=" + quote("Invalid plant type"),
            status_code=303,
        )
    p.scientific_name = scientific_name.strip()
    p.plant_type_id = plant_type_id
    p.life_cycle = life_cycle
    p.common_names = json.dumps(_comma_list(common_names))
    p.edible_parts = json.dumps(_comma_list(edible_parts))
    p.native_regions = native_regions.strip() or None
    p.toxicity_notes = toxicity_notes.strip() or None
    _apply_plant_image_fields(p, image_url, image_file, clear_image)
    try:
        db.commit()
    except Exception as e:
        db.rollback()
        return RedirectResponse(
            url=f"/admin/plants/{plant_id}/edit?error=" + quote(str(e)),
            status_code=303,
        )
    return RedirectResponse(url=f"/admin/plants/{plant_id}/profiles", status_code=303)


@router.post("/plants/{plant_id}/delete")
def admin_plant_delete(plant_id: int, db: Session = Depends(get_db)):
    p = db.get(Plant, plant_id)
    if not p:
        raise HTTPException(404)
    clear_uploaded_images(plant_id)
    gids = list(db.scalars(select(GrowingProfile.id).where(GrowingProfile.plant_id == plant_id)))
    for gid in gids:
        _delete_profile_cascade(db, gid)
    db.delete(p)
    db.commit()
    return RedirectResponse(url="/admin/plants", status_code=303)


# --- Profiles ---
@router.get("/plants/{plant_id}/profiles", response_class=HTMLResponse)
def admin_profiles_for_plant(request: Request, plant_id: int, db: Session = Depends(get_db)):
    p = db.get(Plant, plant_id)
    if not p:
        raise HTTPException(404)
    profiles = db.scalars(
        select(GrowingProfile)
        .where(GrowingProfile.plant_id == plant_id)
        .options(joinedload(GrowingProfile.steps))
    ).unique().all()
    envs = {e.id: e for e in db.scalars(select(EnvironmentCondition)).all()}
    meds = {m.id: m for m in db.scalars(select(GrowingMedium)).all()}
    rows = []
    for pr in profiles:
        rows.append(
            {
                "id": pr.id,
                "env": envs.get(pr.environment_condition_id),
                "medium": meds.get(pr.medium_id),
                "summary": (pr.summary or "")[:80],
                "difficulty": pr.difficulty,
                "confidence": pr.confidence_level,
                "step_count": len(pr.steps),
            }
        )
    return templates.TemplateResponse(
        "admin/profiles_list.html",
        {"request": request, "plant": p, "profiles": rows, "title": f"Profiles — {p.scientific_name}"},
    )


@router.get("/plants/{plant_id}/profiles/new", response_class=HTMLResponse)
def admin_profile_new_form(request: Request, plant_id: int, db: Session = Depends(get_db)):
    p = db.get(Plant, plant_id)
    if not p:
        raise HTTPException(404)
    envs = db.scalars(select(EnvironmentCondition).order_by(EnvironmentCondition.name)).all()
    meds = db.scalars(select(GrowingMedium).order_by(GrowingMedium.name)).all()
    sources = db.scalars(select(Source).order_by(Source.title)).all()
    return templates.TemplateResponse(
        "admin/profile_form.html",
        {
            "request": request,
            "title": "New growing profile",
            "plant": p,
            "profile": None,
            "envs": envs,
            "meds": meds,
            "sources": sources,
            "difficulties": DIFFICULTIES,
            "confidence_levels": CONFIDENCE_LEVELS,
            "selected_sources": [],
            "error": request.query_params.get("error"),
        },
    )


@router.post("/plants/{plant_id}/profiles/new")
def admin_profile_new(
    plant_id: int,
    db: Session = Depends(get_db),
    environment_condition_id: int = Form(...),
    medium_id: int = Form(...),
    difficulty: str = Form(...),
    confidence_level: str = Form(...),
    summary: str = Form(""),
    climate_context: str = Form(""),
    hardiness_zone_min: str = Form(""),
    hardiness_zone_max: str = Form(""),
    source_id: list[int] = Form(default=[]),
):
    p = db.get(Plant, plant_id)
    if not p:
        raise HTTPException(404)
    if difficulty not in DIFFICULTIES or confidence_level not in CONFIDENCE_LEVELS:
        return RedirectResponse(
            url=f"/admin/plants/{plant_id}/profiles/new?error=" + quote("Invalid difficulty or confidence"),
            status_code=303,
        )
    zmin = int(hardiness_zone_min) if hardiness_zone_min and hardiness_zone_min.strip().lstrip("-").isdigit() else None
    zmax = int(hardiness_zone_max) if hardiness_zone_max and hardiness_zone_max.strip().lstrip("-").isdigit() else None
    gp = GrowingProfile(
        plant_id=plant_id,
        environment_condition_id=environment_condition_id,
        medium_id=medium_id,
        hardiness_zone_min=zmin,
        hardiness_zone_max=zmax,
        summary=summary.strip() or None,
        climate_context=climate_context.strip() or None,
        difficulty=difficulty,
        confidence_level=confidence_level,
    )
    db.add(gp)
    try:
        db.flush()
    except Exception as e:
        db.rollback()
        return RedirectResponse(
            url=f"/admin/plants/{plant_id}/profiles/new?error=" + quote(str(e)),
            status_code=303,
        )
    _sync_profile_citations(db, gp.id, source_id)
    try:
        _assert_profile_citations(db, gp.id, confidence_level)
    except ValueError as e:
        db.rollback()
        return RedirectResponse(
            url=f"/admin/plants/{plant_id}/profiles/new?error=" + quote(str(e)),
            status_code=303,
        )
    db.commit()
    return RedirectResponse(url=f"/admin/profiles/{gp.id}/edit", status_code=303)


@router.get("/profiles/{profile_id}/edit", response_class=HTMLResponse)
def admin_profile_edit_form(request: Request, profile_id: int, db: Session = Depends(get_db)):
    pr = db.get(GrowingProfile, profile_id)
    if not pr:
        raise HTTPException(404)
    p = db.get(Plant, pr.plant_id)
    envs = db.scalars(select(EnvironmentCondition).order_by(EnvironmentCondition.name)).all()
    meds = db.scalars(select(GrowingMedium).order_by(GrowingMedium.name)).all()
    sources = db.scalars(select(Source).order_by(Source.title)).all()
    sel = list(
        db.scalars(
            select(Citation.source_id).where(
                Citation.target_type == "profile",
                Citation.target_id == profile_id,
            )
        ).all()
    )
    pr = db.scalars(
        select(GrowingProfile)
        .where(GrowingProfile.id == profile_id)
        .options(joinedload(GrowingProfile.steps), joinedload(GrowingProfile.requirements))
    ).unique().one()
    hazards = db.scalars(select(Hazard).order_by(Hazard.kind, Hazard.name)).all()
    ph_rows = db.execute(
        text(
            "SELECT h.id AS hazard_id, h.name AS hazard_name, h.kind AS hazard_kind, "
            "g.mitigation_detail, g.evidence_notes "
            "FROM growing_profile_hazard g JOIN hazard h ON h.id = g.hazard_id "
            "WHERE g.growing_profile_id = :pid ORDER BY h.kind, h.name"
        ),
        {"pid": profile_id},
    ).all()
    return templates.TemplateResponse(
        "admin/profile_edit.html",
        {
            "request": request,
            "title": "Edit growing profile",
            "plant": p,
            "profile": pr,
            "envs": envs,
            "meds": meds,
            "sources": sources,
            "selected_sources": sel,
            "difficulties": DIFFICULTIES,
            "confidence_levels": CONFIDENCE_LEVELS,
            "hazards": hazards,
            "profile_hazards": ph_rows,
            "error": request.query_params.get("error"),
        },
    )


@router.post("/profiles/{profile_id}/edit")
def admin_profile_edit(
    profile_id: int,
    db: Session = Depends(get_db),
    environment_condition_id: int = Form(...),
    medium_id: int = Form(...),
    difficulty: str = Form(...),
    confidence_level: str = Form(...),
    summary: str = Form(""),
    climate_context: str = Form(""),
    hardiness_zone_min: str = Form(""),
    hardiness_zone_max: str = Form(""),
    source_id: list[int] = Form(default=[]),
):
    pr = db.get(GrowingProfile, profile_id)
    if not pr:
        raise HTTPException(404)
    if difficulty not in DIFFICULTIES or confidence_level not in CONFIDENCE_LEVELS:
        return RedirectResponse(
            url=f"/admin/profiles/{profile_id}/edit?error=" + quote("Invalid difficulty or confidence"),
            status_code=303,
        )
    zmin = int(hardiness_zone_min) if hardiness_zone_min and hardiness_zone_min.strip().lstrip("-").isdigit() else None
    zmax = int(hardiness_zone_max) if hardiness_zone_max and hardiness_zone_max.strip().lstrip("-").isdigit() else None
    pr.environment_condition_id = environment_condition_id
    pr.medium_id = medium_id
    pr.difficulty = difficulty
    pr.confidence_level = confidence_level
    pr.summary = summary.strip() or None
    pr.climate_context = climate_context.strip() or None
    pr.hardiness_zone_min = zmin
    pr.hardiness_zone_max = zmax
    _sync_profile_citations(db, profile_id, source_id)
    try:
        _assert_profile_citations(db, profile_id, confidence_level)
    except ValueError as e:
        db.rollback()
        return RedirectResponse(
            url=f"/admin/profiles/{profile_id}/edit?error=" + quote(str(e)),
            status_code=303,
        )
    try:
        db.commit()
    except Exception as e:
        db.rollback()
        return RedirectResponse(
            url=f"/admin/profiles/{profile_id}/edit?error=" + quote(str(e)),
            status_code=303,
        )
    return RedirectResponse(url=f"/admin/profiles/{profile_id}/edit", status_code=303)


@router.post("/profiles/{profile_id}/delete")
def admin_profile_delete(profile_id: int, db: Session = Depends(get_db)):
    pr = db.get(GrowingProfile, profile_id)
    if not pr:
        raise HTTPException(404)
    pid = pr.plant_id
    _delete_profile_cascade(db, profile_id)
    db.commit()
    return RedirectResponse(url=f"/admin/plants/{pid}/profiles", status_code=303)


# --- Steps ---
@router.get("/profiles/{profile_id}/steps/new", response_class=HTMLResponse)
def admin_step_new_form(request: Request, profile_id: int, db: Session = Depends(get_db)):
    pr = db.get(GrowingProfile, profile_id)
    if not pr:
        raise HTTPException(404)
    next_order = (db.scalar(select(func.max(GrowingStep.step_order)).where(GrowingStep.growing_profile_id == profile_id)) or 0) + 1
    return templates.TemplateResponse(
        "admin/step_form.html",
        {
            "request": request,
            "title": "New step",
            "profile": pr,
            "step": None,
            "default_order": next_order,
            "error": request.query_params.get("error"),
        },
    )


@router.post("/profiles/{profile_id}/steps/new")
def admin_step_new(
    profile_id: int,
    db: Session = Depends(get_db),
    step_order: int = Form(...),
    title: str = Form(...),
    body: str = Form(...),
    equipment: str = Form(""),
    duration_days: str = Form(""),
):
    pr = db.get(GrowingProfile, profile_id)
    if not pr:
        raise HTTPException(404)
    dur = int(duration_days) if duration_days and duration_days.strip().isdigit() else None
    st = GrowingStep(
        growing_profile_id=profile_id,
        step_order=step_order,
        title=title.strip(),
        body=body.strip(),
        equipment=equipment.strip() or None,
        duration_days=dur,
    )
    db.add(st)
    try:
        db.commit()
    except Exception as e:
        db.rollback()
        return RedirectResponse(
            url=f"/admin/profiles/{profile_id}/steps/new?error=" + quote(str(e)),
            status_code=303,
        )
    return RedirectResponse(url=f"/admin/profiles/{profile_id}/edit", status_code=303)


@router.get("/steps/{step_id}/edit", response_class=HTMLResponse)
def admin_step_edit_form(request: Request, step_id: int, db: Session = Depends(get_db)):
    st = db.get(GrowingStep, step_id)
    if not st:
        raise HTTPException(404)
    pr = db.get(GrowingProfile, st.growing_profile_id)
    return templates.TemplateResponse(
        "admin/step_form.html",
        {
            "request": request,
            "title": "Edit step",
            "profile": pr,
            "step": st,
            "default_order": st.step_order,
            "error": request.query_params.get("error"),
        },
    )


@router.post("/steps/{step_id}/edit")
def admin_step_edit(
    step_id: int,
    db: Session = Depends(get_db),
    step_order: int = Form(...),
    title: str = Form(...),
    body: str = Form(...),
    equipment: str = Form(""),
    duration_days: str = Form(""),
):
    st = db.get(GrowingStep, step_id)
    if not st:
        raise HTTPException(404)
    pid = st.growing_profile_id
    dur = int(duration_days) if duration_days and duration_days.strip().isdigit() else None
    st.step_order = step_order
    st.title = title.strip()
    st.body = body.strip()
    st.equipment = equipment.strip() or None
    st.duration_days = dur
    try:
        db.commit()
    except Exception as e:
        db.rollback()
        return RedirectResponse(
            url=f"/admin/steps/{step_id}/edit?error=" + quote(str(e)),
            status_code=303,
        )
    return RedirectResponse(url=f"/admin/profiles/{pid}/edit", status_code=303)


@router.post("/steps/{step_id}/delete")
def admin_step_delete(step_id: int, db: Session = Depends(get_db)):
    st = db.get(GrowingStep, step_id)
    if not st:
        raise HTTPException(404)
    pid = st.growing_profile_id
    db.execute(delete(Citation).where(Citation.target_type == "step", Citation.target_id == step_id))
    db.delete(st)
    db.commit()
    return RedirectResponse(url=f"/admin/profiles/{pid}/edit", status_code=303)


# --- Requirements ---
@router.get("/profiles/{profile_id}/requirements/new", response_class=HTMLResponse)
def admin_req_new_form(request: Request, profile_id: int, db: Session = Depends(get_db)):
    pr = db.get(GrowingProfile, profile_id)
    if not pr:
        raise HTTPException(404)
    return templates.TemplateResponse(
        "admin/requirement_form.html",
        {
            "request": request,
            "title": "New requirement",
            "profile": pr,
            "req": None,
            "categories": REQ_CATEGORIES,
            "error": request.query_params.get("error"),
        },
    )


@router.post("/profiles/{profile_id}/requirements/new")
def admin_req_new(
    profile_id: int,
    db: Session = Depends(get_db),
    category: str = Form(...),
    value_min: str = Form(""),
    value_max: str = Form(""),
    unit: str = Form(""),
    notes: str = Form(""),
):
    pr = db.get(GrowingProfile, profile_id)
    if not pr:
        raise HTTPException(404)
    if category not in REQ_CATEGORIES:
        return RedirectResponse(
            url=f"/admin/profiles/{profile_id}/requirements/new?error=" + quote("Invalid category"),
            status_code=303,
        )
    vm = float(value_min) if value_min and value_min.strip() else None
    vx = float(value_max) if value_max and value_max.strip() else None
    r = Requirement(
        growing_profile_id=profile_id,
        category=category,
        value_min=vm,
        value_max=vx,
        unit=unit.strip() or None,
        notes=notes.strip() or None,
    )
    db.add(r)
    db.commit()
    return RedirectResponse(url=f"/admin/profiles/{profile_id}/edit", status_code=303)


@router.get("/requirements/{req_id}/edit", response_class=HTMLResponse)
def admin_req_edit_form(request: Request, req_id: int, db: Session = Depends(get_db)):
    r = db.get(Requirement, req_id)
    if not r:
        raise HTTPException(404)
    pr = db.get(GrowingProfile, r.growing_profile_id)
    return templates.TemplateResponse(
        "admin/requirement_form.html",
        {
            "request": request,
            "title": "Edit requirement",
            "profile": pr,
            "req": r,
            "categories": REQ_CATEGORIES,
            "error": request.query_params.get("error"),
        },
    )


@router.post("/requirements/{req_id}/edit")
def admin_req_edit(
    req_id: int,
    db: Session = Depends(get_db),
    category: str = Form(...),
    value_min: str = Form(""),
    value_max: str = Form(""),
    unit: str = Form(""),
    notes: str = Form(""),
):
    r = db.get(Requirement, req_id)
    if not r:
        raise HTTPException(404)
    pid = r.growing_profile_id
    if category not in REQ_CATEGORIES:
        return RedirectResponse(
            url=f"/admin/requirements/{req_id}/edit?error=" + quote("Invalid category"),
            status_code=303,
        )
    r.category = category
    r.value_min = float(value_min) if value_min and value_min.strip() else None
    r.value_max = float(value_max) if value_max and value_max.strip() else None
    r.unit = unit.strip() or None
    r.notes = notes.strip() or None
    db.commit()
    return RedirectResponse(url=f"/admin/profiles/{pid}/edit", status_code=303)


@router.post("/requirements/{req_id}/delete")
def admin_req_delete(req_id: int, db: Session = Depends(get_db)):
    r = db.get(Requirement, req_id)
    if not r:
        raise HTTPException(404)
    pid = r.growing_profile_id
    db.delete(r)
    db.commit()
    return RedirectResponse(url=f"/admin/profiles/{pid}/edit", status_code=303)


# --- Profile hazards ---
@router.post("/profiles/{profile_id}/hazards/add")
def admin_profile_hazard_add(
    profile_id: int,
    db: Session = Depends(get_db),
    hazard_id: int = Form(...),
    mitigation_detail: str = Form(""),
    evidence_notes: str = Form(""),
):
    pr = db.get(GrowingProfile, profile_id)
    if not pr:
        raise HTTPException(404)
    if not db.get(Hazard, hazard_id):
        raise HTTPException(404)
    db.execute(
        text(
            "INSERT OR REPLACE INTO growing_profile_hazard "
            "(growing_profile_id, hazard_id, mitigation_detail, evidence_notes) "
            "VALUES (:pid, :hid, :md, :en)"
        ),
        {
            "pid": profile_id,
            "hid": hazard_id,
            "md": mitigation_detail.strip() or None,
            "en": evidence_notes.strip() or None,
        },
    )
    db.commit()
    return RedirectResponse(url=f"/admin/profiles/{profile_id}/edit", status_code=303)


@router.post("/profiles/{profile_id}/hazards/{hazard_id}/delete")
def admin_profile_hazard_delete(profile_id: int, hazard_id: int, db: Session = Depends(get_db)):
    db.execute(
        text("DELETE FROM growing_profile_hazard WHERE growing_profile_id=:pid AND hazard_id=:hid"),
        {"pid": profile_id, "hid": hazard_id},
    )
    db.commit()
    return RedirectResponse(url=f"/admin/profiles/{profile_id}/edit", status_code=303)
