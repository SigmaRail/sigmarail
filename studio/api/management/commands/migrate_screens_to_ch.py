"""Migrate SQLite SavedScreen rows into ClickHouse strategy_screens.

Usage (with SCREEN_STORE still sqlite for ORM read, then switch to ch):

  export SCREEN_STORE=sqlite
  python manage.py migrate_screens_to_ch
  export SCREEN_STORE=ch
"""

from __future__ import annotations

from django.core.management.base import BaseCommand

from api.models import SavedScreen
from screens.screen_store import ClickHouseScreenRepository, ScreenNameConflictError


class Command(BaseCommand):
    help = "Copy SQLite SavedScreen rows into ClickHouse strategy_screens"

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="List screens that would be migrated without writing",
        )

    def handle(self, *args, **options) -> None:
        dry = bool(options.get("dry_run"))
        ch_repo = ClickHouseScreenRepository()
        existing_names = {s.name for s in ch_repo.list()}
        created = 0
        skipped = 0
        for row in SavedScreen.objects.all().order_by("id"):
            if row.name in existing_names:
                self.stdout.write(f"skip (exists): {row.name}")
                skipped += 1
                continue
            if dry:
                self.stdout.write(f"would create: {row.name} (sqlite id={row.pk})")
                created += 1
                continue
            try:
                rec = ch_repo.create(name=row.name, spec=row.spec if isinstance(row.spec, dict) else {})
            except ScreenNameConflictError:
                self.stdout.write(f"skip (race): {row.name}")
                skipped += 1
                continue
            self.stdout.write(f"created: {row.name} → {rec.id}")
            created += 1
            existing_names.add(row.name)
        self.stdout.write(self.style.SUCCESS(f"done created={created} skipped={skipped}"))
