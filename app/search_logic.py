"""Search across SQLite-backed tables (ILIKE on multiple columns)."""

from __future__ import annotations

from typing import Any
from urllib.parse import quote

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.models import (
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


def _safe_pattern(q: str) -> str:
    t = (q or "").strip()
    t = t.replace("%", "").replace("_", "")
    return f"%{t}%"


def _snip(s: str | None, max_len: int = 160) -> str:
    if not s:
        return ""
    s = " ".join(s.split())
    if len(s) <= max_len:
        return s
    return s[: max_len - 1] + "…"


def _hit(
    title: str,
    url: str,
    meta: str = "",
    snippet: str = "",
    image_url: str | None = None,
) -> dict[str, str | None]:
    return {
        "title": title,
        "url": url,
        "meta": meta,
        "snippet": snippet,
        "image_url": image_url,
    }


def global_search(db: Session, q: str) -> dict[str, Any]:
    raw = (q or "").strip()
    if len(raw) < 2:
        return {"ok": False, "message": "Type at least 2 characters.", "query": raw}

    pattern = _safe_pattern(raw)
    out: dict[str, Any] = {
        "ok": True,
        "query": raw,
        "plants": [],
        "profiles": [],
        "steps": [],
        "requirements": [],
        "environments": [],
        "media": [],
        "hazards": [],
        "sources": [],
        "plant_types": [],
    }

    p_conds = or_(
        Plant.scientific_name.ilike(pattern),
        Plant.common_names.ilike(pattern),
        Plant.native_regions.ilike(pattern),
        Plant.toxicity_notes.ilike(pattern),
        Plant.edible_parts.ilike(pattern),
    )
    for p in db.scalars(select(Plant).where(p_conds).order_by(Plant.scientific_name).limit(50)):
        bits = [p.scientific_name]
        if p.native_regions:
            bits.append(_snip(p.native_regions, 80))
        out["plants"].append(
            _hit(
                p.scientific_name,
                f"/plant/{p.id}",
                "Plant",
                _snip(" · ".join(bits)),
                image_url=p.image_url,
            )
        )

    pr_rows = db.execute(
        select(
            GrowingProfile.id,
            Plant.id,
            Plant.scientific_name,
            Plant.image_url,
            EnvironmentCondition.name,
            GrowingMedium.name,
            GrowingProfile.summary,
            GrowingProfile.climate_context,
        )
        .join(Plant, GrowingProfile.plant_id == Plant.id)
        .join(EnvironmentCondition, GrowingProfile.environment_condition_id == EnvironmentCondition.id)
        .join(GrowingMedium, GrowingProfile.medium_id == GrowingMedium.id)
        .where(
            or_(
                GrowingProfile.summary.ilike(pattern),
                GrowingProfile.climate_context.ilike(pattern),
                EnvironmentCondition.name.ilike(pattern),
                EnvironmentCondition.code.ilike(pattern),
                EnvironmentCondition.description.ilike(pattern),
                GrowingMedium.name.ilike(pattern),
                GrowingMedium.description.ilike(pattern),
            )
        )
        .distinct()
        .limit(40)
    ).all()
    for row in pr_rows:
        _pr_id, pid, sci, pimg, envn, medn, summ, cctx = row[0], row[1], row[2], row[3], row[4], row[5], row[6], row[7]
        snip = _snip(summ or "") or _snip(cctx or "")
        out["profiles"].append(
            _hit(
                f"{sci}, {envn}",
                f"/plant/{pid}",
                f"Growing profile · {medn}",
                snip,
                image_url=pimg,
            )
        )

    st_rows = db.execute(
        select(GrowingStep.title, GrowingStep.body, Plant.id, Plant.scientific_name, Plant.image_url)
        .join(GrowingProfile, GrowingStep.growing_profile_id == GrowingProfile.id)
        .join(Plant, GrowingProfile.plant_id == Plant.id)
        .where(
            or_(
                GrowingStep.title.ilike(pattern),
                GrowingStep.body.ilike(pattern),
                GrowingStep.equipment.ilike(pattern),
            )
        )
        .limit(40)
    ).all()
    for title, body, plant_id, sci, pimg in st_rows:
        out["steps"].append(
            _hit(title, f"/plant/{plant_id}", f"Step · {sci}", _snip(body or ""), image_url=pimg)
        )

    rq_rows = db.execute(
        select(Requirement.category, Requirement.notes, Plant.id, Plant.scientific_name, Plant.image_url)
        .join(GrowingProfile, Requirement.growing_profile_id == GrowingProfile.id)
        .join(Plant, GrowingProfile.plant_id == Plant.id)
        .where(
            or_(
                Requirement.category.ilike(pattern),
                Requirement.notes.ilike(pattern),
                Requirement.unit.ilike(pattern),
            )
        )
        .limit(40)
    ).all()
    for cat, notes, plant_id, sci, pimg in rq_rows:
        out["requirements"].append(
            _hit(cat, f"/plant/{plant_id}", f"Requirement · {sci}", _snip(notes or ""), image_url=pimg)
        )

    for e in db.scalars(
        select(EnvironmentCondition)
        .where(
            or_(
                EnvironmentCondition.code.ilike(pattern),
                EnvironmentCondition.name.ilike(pattern),
                EnvironmentCondition.description.ilike(pattern),
            )
        )
        .order_by(EnvironmentCondition.name)
        .limit(25)
    ):
        out["environments"].append(
            _hit(
                e.name,
                f"/search?q={quote(e.name)}",
                "Environment" + (" · speculative" if e.is_speculative else ""),
                _snip(e.description or ""),
                image_url=None,
            )
        )

    for m in db.scalars(
        select(GrowingMedium)
        .where(or_(GrowingMedium.name.ilike(pattern), GrowingMedium.description.ilike(pattern)))
        .order_by(GrowingMedium.name)
        .limit(25)
    ):
        out["media"].append(
            _hit(m.name, f"/search?q={quote(m.name)}", "Growing medium", _snip(m.description or ""), image_url=None)
        )

    for h in db.scalars(
        select(Hazard)
        .where(
            or_(
                Hazard.name.ilike(pattern),
                Hazard.description.ilike(pattern),
                Hazard.mitigation_summary.ilike(pattern),
                Hazard.kind.ilike(pattern),
            )
        )
        .order_by(Hazard.name)
        .limit(25)
    ):
        hz_meta = "Growing issue" if h.kind == "growing_issue" else "Food safety"
        out["hazards"].append(
            _hit(
                h.name,
                f"/search?q={quote(h.name)}",
                hz_meta,
                _snip(h.mitigation_summary or h.description or ""),
                image_url=None,
            )
        )

    for s in db.scalars(
        select(Source)
        .where(
            or_(
                Source.title.ilike(pattern),
                Source.url.ilike(pattern),
                Source.publisher.ilike(pattern),
            )
        )
        .order_by(Source.title)
        .limit(25)
    ):
        out["sources"].append(
            _hit(
                s.title,
                f"/admin/sources/{s.id}/edit",
                f"Source · {s.source_type}",
                _snip(s.url or s.publisher or ""),
                image_url=None,
            )
        )

    for t in db.scalars(
        select(PlantType)
        .where(or_(PlantType.name.ilike(pattern), PlantType.description.ilike(pattern)))
        .order_by(PlantType.name)
        .limit(25)
    ):
        out["plant_types"].append(
            _hit(t.name, f"/search?q={quote(t.name)}", "Plant category", _snip(t.description or ""), image_url=None)
        )

    total = sum(len(out[k]) for k in ("plants", "profiles", "steps", "requirements", "environments", "media", "hazards", "sources", "plant_types"))
    out["total"] = total
    return out
