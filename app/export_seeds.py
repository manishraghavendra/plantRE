"""Export current SQLite data to JSON files compatible with seed_loader.

Run from project root:
  python -m app.export_seeds

Writes to seeds/export/ by default (does not overwrite seeds/*.json).
Copy files from seeds/export/ into seeds/ when you want them to be the next reseed baseline.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from sqlalchemy import select, text
from sqlalchemy.orm import Session, joinedload

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


def _write(path: Path, data: list | dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def run_export(out_dir: Path | None = None) -> Path:
    init_db()
    out = out_dir or (settings.seeds_dir / "export")
    out.mkdir(parents=True, exist_ok=True)

    with Session(engine) as session:
        plant_types = [
            {"name": pt.name, "description": pt.description}
            for pt in session.scalars(select(PlantType).order_by(PlantType.name)).all()
        ]
        growing_media = [
            {"name": gm.name, "description": gm.description}
            for gm in session.scalars(select(GrowingMedium).order_by(GrowingMedium.name)).all()
        ]
        envs = [
            {
                "code": e.code,
                "name": e.name,
                "description": e.description,
                "severity_scale": e.severity_scale,
                "is_speculative": bool(e.is_speculative),
            }
            for e in session.scalars(select(EnvironmentCondition).order_by(EnvironmentCondition.code)).all()
        ]
        factors = [
            {"name": sf.name, "description": sf.description}
            for sf in session.scalars(select(SurvivalFactor).order_by(SurvivalFactor.name)).all()
        ]
        env_sf: list[dict] = []
        for link in session.scalars(select(EnvironmentConditionSurvivalFactor)).all():
            ec = session.get(EnvironmentCondition, link.environment_condition_id)
            sf = session.get(SurvivalFactor, link.survival_factor_id)
            if ec and sf:
                env_sf.append(
                    {
                        "environment_code": ec.code,
                        "survival_factor_name": sf.name,
                        "relevance": link.relevance,
                    }
                )
        hazards = [
            {
                "name": hz.name,
                "kind": hz.kind,
                "description": hz.description,
                "mitigation_summary": hz.mitigation_summary,
            }
            for hz in session.scalars(select(Hazard).order_by(Hazard.name)).all()
        ]
        sources = [
            {
                "title": s.title,
                "url": s.url,
                "publisher": s.publisher,
                "year": s.year,
                "source_type": s.source_type,
            }
            for s in session.scalars(select(Source).order_by(Source.title)).all()
        ]

        plants_out: list[dict] = []
        for p in session.scalars(select(Plant).order_by(Plant.scientific_name)).all():
            pt = session.get(PlantType, p.plant_type_id)
            plants_out.append(
                {
                    "scientific_name": p.scientific_name,
                    "common_names": json.loads(p.common_names) if p.common_names else [],
                    "plant_type_name": pt.name if pt else "",
                    "life_cycle": p.life_cycle,
                    "native_regions": p.native_regions,
                    "edible_parts": json.loads(p.edible_parts) if p.edible_parts else [],
                    "toxicity_notes": p.toxicity_notes,
                    **({"image_url": p.image_url} if p.image_url else {}),
                }
            )

        profiles_out: list[dict] = []
        profiles = session.scalars(
            select(GrowingProfile)
            .options(joinedload(GrowingProfile.steps), joinedload(GrowingProfile.requirements))
            .order_by(GrowingProfile.id)
        ).unique().all()

        for gp in profiles:
            plant = session.get(Plant, gp.plant_id)
            ec = session.get(EnvironmentCondition, gp.environment_condition_id)
            med = session.get(GrowingMedium, gp.medium_id)
            if not plant or not ec or not med:
                continue

            steps = [
                {
                    "step_order": s.step_order,
                    "title": s.title,
                    "body": s.body,
                    "duration_days": s.duration_days,
                    "equipment": s.equipment,
                }
                for s in sorted(gp.steps, key=lambda x: x.step_order)
            ]
            reqs = [
                {
                    "category": r.category,
                    "value_min": r.value_min,
                    "value_max": r.value_max,
                    "unit": r.unit,
                    "notes": r.notes,
                }
                for r in gp.requirements
            ]
            hz_rows = session.execute(
                text(
                    "SELECT h.name, g.mitigation_detail, g.evidence_notes "
                    "FROM growing_profile_hazard g JOIN hazard h ON h.id = g.hazard_id "
                    "WHERE g.growing_profile_id = :pid"
                ),
                {"pid": gp.id},
            ).all()
            hazard_links = [
                {"hazard_name": row[0], "mitigation_detail": row[1], "evidence_notes": row[2]}
                for row in hz_rows
            ]
            cites = []
            for c in session.scalars(
                select(Citation).where(Citation.target_type == "profile", Citation.target_id == gp.id)
            ).all():
                src = session.get(Source, c.source_id)
                if not src:
                    continue
                cite = {
                    "source_title": src.title,
                    "target": "profile",
                    "quote": c.quote,
                    "page": c.page,
                }
                cites.append(cite)

            block: dict = {
                "plant_scientific_name": plant.scientific_name,
                "environment_code": ec.code,
                "medium_name": med.name,
                "hardiness_zone_min": gp.hardiness_zone_min,
                "hardiness_zone_max": gp.hardiness_zone_max,
                "summary": gp.summary,
                "difficulty": gp.difficulty,
                "confidence_level": gp.confidence_level,
                "last_reviewed_at": gp.last_reviewed_at,
                "steps": steps,
                "requirements": reqs,
                "hazard_links": hazard_links,
                "citations": cites,
            }
            if gp.climate_context:
                block["climate_context"] = gp.climate_context
            profiles_out.append(block)

    _write(out / "plant_types.json", plant_types)
    _write(out / "growing_media.json", growing_media)
    _write(out / "environment_conditions.json", envs)
    _write(out / "survival_factors.json", factors)
    _write(out / "environment_survival_factors.json", env_sf)
    _write(out / "hazards.json", hazards)
    _write(out / "sources.json", sources)
    _write(out / "plants.json", plants_out)
    _write(out / "growing_profiles.json", profiles_out)

    readme = out / "README.txt"
    readme.write_text(
        "These JSON files match the format expected by app.seed_loader.run_seed().\n\n"
        "To use them as your new baseline:\n"
        "  1. Back up your current seeds/ folder if needed.\n"
        "  2. Copy (or move) all .json files from this export/ folder into seeds/.\n"
        "  3. Run: python -m app.seed_loader\n\n"
        "Warning: seeding clears the database and reloads from seeds/*.json.\n",
        encoding="utf-8",
    )

    return out


def main():
    parser = argparse.ArgumentParser(description="Export DB to seed-compatible JSON.")
    parser.add_argument(
        "-o",
        "--out",
        type=Path,
        default=None,
        help=f"Output directory (default: {settings.seeds_dir / 'export'})",
    )
    args = parser.parse_args()
    out = run_export(args.out)
    print(f"Export wrote {len(list(out.glob('*.json')))} JSON files to: {out.resolve()}")
    print("See export/README.txt for how to merge into seeds/ and reseed.")


if __name__ == "__main__":
    main()
