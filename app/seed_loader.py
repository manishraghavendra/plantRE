"""Load JSON seeds into SQLite. Clears data tables then reloads (repeatable)."""

from __future__ import annotations

import json

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.config import settings
from app.database import engine, init_db
from app.models import (
    Citation,
    EnvironmentCondition,
    EnvironmentConditionSurvivalFactor,
    GrowingMedium,
    GrowingProfile,
    GrowingStep,
    Hazard,
    Plant,
    PlantType,
    Requirement,
    Source,
    SurvivalFactor,
)


def _load_json(name: str) -> list | dict:
    path = settings.seeds_dir / name
    return json.loads(path.read_text(encoding="utf-8"))


CLEAR_ORDER = [
    "citation",
    "growing_step",
    "requirement",
    "growing_profile_resource",
    "growing_profile_hazard",
    "calendar_task",
    "plant_relationship",
    "growing_profile",
    "plant",
    "environment_condition_survival_factor",
    "environment_condition",
    "survival_factor",
    "plant_type",
    "growing_medium",
    "hazard",
    "resource",
    "source",
]


def clear_data(session: Session) -> None:
    session.execute(text("PRAGMA foreign_keys=OFF"))
    for tbl in CLEAR_ORDER:
        session.execute(text(f"DELETE FROM {tbl}"))
    session.execute(text("PRAGMA foreign_keys=ON"))


def assert_profile_citations(session: Session, profile_id: int, confidence_level: str) -> None:
    if confidence_level == "speculative":
        return
    n = session.scalar(
        select(func.count())
        .select_from(Citation)
        .where(Citation.target_type == "profile", Citation.target_id == profile_id)
    )
    if not n:
        raise ValueError(
            f"Growing profile id={profile_id} has confidence_level={confidence_level!r} "
            "but no profile-level citations. Add at least one citation with target=profile."
        )


def run_seed() -> None:
    init_db()
    plant_types = _load_json("plant_types.json")
    growing_media = _load_json("growing_media.json")
    envs = _load_json("environment_conditions.json")
    factors = _load_json("survival_factors.json")
    env_factor_links = _load_json("environment_survival_factors.json")
    hazards = _load_json("hazards.json")
    sources = _load_json("sources.json")
    plants = _load_json("plants.json")
    profiles = _load_json("growing_profiles.json")

    with Session(engine) as session:
        clear_data(session)

        type_by_name: dict[str, int] = {}
        for row in plant_types:
            pt = PlantType(name=row["name"], description=row.get("description"))
            session.add(pt)
            session.flush()
            type_by_name[pt.name] = pt.id

        medium_by_name: dict[str, int] = {}
        for row in growing_media:
            gm = GrowingMedium(name=row["name"], description=row.get("description"))
            session.add(gm)
            session.flush()
            medium_by_name[gm.name] = gm.id

        env_by_code: dict[str, int] = {}
        for row in envs:
            ec = EnvironmentCondition(
                code=row["code"],
                name=row["name"],
                description=row.get("description"),
                severity_scale=row.get("severity_scale"),
                is_speculative=bool(row.get("is_speculative", False)),
            )
            session.add(ec)
            session.flush()
            env_by_code[ec.code] = ec.id

        factor_by_name: dict[str, int] = {}
        for row in factors:
            sf = SurvivalFactor(name=row["name"], description=row.get("description"))
            session.add(sf)
            session.flush()
            factor_by_name[sf.name] = sf.id

        for link in env_factor_links:
            session.add(
                EnvironmentConditionSurvivalFactor(
                    environment_condition_id=env_by_code[link["environment_code"]],
                    survival_factor_id=factor_by_name[link["survival_factor_name"]],
                    relevance=link.get("relevance"),
                )
            )

        hazard_by_name: dict[str, int] = {}
        for row in hazards:
            hz = Hazard(
                name=row["name"],
                description=row.get("description"),
                mitigation_summary=row.get("mitigation_summary"),
                kind=row.get("kind") or "food_safety",
            )
            session.add(hz)
            session.flush()
            hazard_by_name[hz.name] = hz.id

        source_by_title: dict[str, int] = {}
        for row in sources:
            src = Source(
                title=row["title"],
                url=row.get("url"),
                publisher=row.get("publisher"),
                year=row.get("year"),
                source_type=row["source_type"],
            )
            session.add(src)
            session.flush()
            source_by_title[src.title] = src.id

        plant_by_scientific: dict[str, int] = {}
        for row in plants:
            p = Plant(
                scientific_name=row["scientific_name"],
                common_names=json.dumps(row.get("common_names") or []),
                plant_type_id=type_by_name[row["plant_type_name"]],
                life_cycle=row["life_cycle"],
                native_regions=row.get("native_regions"),
                edible_parts=json.dumps(row.get("edible_parts") or []),
                toxicity_notes=row.get("toxicity_notes"),
                image_url=row.get("image_url"),
            )
            session.add(p)
            session.flush()
            plant_by_scientific[p.scientific_name] = p.id

        for pdata in profiles:
            gp = GrowingProfile(
                plant_id=plant_by_scientific[pdata["plant_scientific_name"]],
                environment_condition_id=env_by_code[pdata["environment_code"]],
                medium_id=medium_by_name[pdata["medium_name"]],
                hardiness_zone_min=pdata.get("hardiness_zone_min"),
                hardiness_zone_max=pdata.get("hardiness_zone_max"),
                summary=pdata.get("summary"),
                difficulty=pdata["difficulty"],
                confidence_level=pdata["confidence_level"],
                last_reviewed_at=pdata.get("last_reviewed_at"),
                climate_context=pdata.get("climate_context"),
            )
            session.add(gp)
            session.flush()

            for s in pdata.get("steps") or []:
                session.add(
                    GrowingStep(
                        growing_profile_id=gp.id,
                        step_order=s["step_order"],
                        title=s["title"],
                        body=s["body"],
                        duration_days=s.get("duration_days"),
                        equipment=s.get("equipment"),
                    )
                )

            for r in pdata.get("requirements") or []:
                session.add(
                    Requirement(
                        growing_profile_id=gp.id,
                        category=r["category"],
                        value_min=r.get("value_min"),
                        value_max=r.get("value_max"),
                        unit=r.get("unit"),
                        notes=r.get("notes"),
                    )
                )

            for hl in pdata.get("hazard_links") or []:
                session.execute(
                    text(
                        """
                        INSERT INTO growing_profile_hazard
                        (growing_profile_id, hazard_id, mitigation_detail, evidence_notes)
                        VALUES (:pid, :hid, :md, :en)
                        """
                    ),
                    {
                        "pid": gp.id,
                        "hid": hazard_by_name[hl["hazard_name"]],
                        "md": hl.get("mitigation_detail"),
                        "en": hl.get("evidence_notes"),
                    },
                )

            for c in pdata.get("citations") or []:
                if c["target"] != "profile":
                    raise ValueError("Seed citations must use target=profile for non-speculative validation")
                session.add(
                    Citation(
                        source_id=source_by_title[c["source_title"]],
                        target_type="profile",
                        target_id=gp.id,
                        quote=c.get("quote"),
                        page=str(c["page"]) if c.get("page") is not None else None,
                    )
                )

            assert_profile_citations(session, gp.id, gp.confidence_level)

        session.commit()


def main():
    run_seed()
    print("Seed completed OK.")


if __name__ == "__main__":
    main()
