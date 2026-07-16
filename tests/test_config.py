from __future__ import annotations

import unittest
from datetime import datetime, timezone

from app.config import (
    CATEGORIES,
    SettingsError,
    base_url_origin,
    default_settings,
    discovered_vehicle_changes,
    next_run_at,
    validate_settings,
    wifi_policy,
)


class SettingsTests(unittest.TestCase):
    def test_defaults_are_generic_and_configurable(self) -> None:
        settings = validate_settings(default_settings())
        self.assertEqual(settings["interface"]["language"], "en")
        self.assertEqual(settings["vehicle"]["name"], "My vehicle")
        self.assertEqual(settings["vehicle"]["model_name"], "")
        self.assertTrue(settings["vehicle"]["auto_detect_profile"])
        self.assertEqual(settings["vehicle"]["recording_layout"], "")
        self.assertEqual(settings["vehicle"]["surveillance_layout"], "")
        self.assertTrue(settings["schedule"]["only_wifi"])
        self.assertEqual(
            settings["content"]["categories"],
            [
                "recordings",
                "trips",
                "charging",
                "automations",
                "key_mappings",
                "telemetry",
            ],
        )
        self.assertEqual(settings["destination"]["type"], "local")
        self.assertEqual(set(settings["retention"]["categories"]), set(CATEGORIES))
        for rule in settings["retention"]["categories"].values():
            self.assertEqual(
                rule,
                {
                    "enabled": False,
                    "value": 30,
                    "unit": "days",
                    "keep_latest_enabled": False,
                    "keep_latest_count": 1,
                },
            )
        self.assertEqual(
            settings["retention"]["storage_limit"],
            {"enabled": False, "max_bytes": 0},
        )

    def test_partial_update_preserves_existing_values(self) -> None:
        current = validate_settings(default_settings())
        current["vehicle"]["device_token"] = "device-token"
        updated = validate_settings(
            {
                "vehicle": {
                    "name": "Family EV",
                    "model_name": "Generic EV",
                    "auto_detect_profile": False,
                },
                "interface": {"language": "pt-BR"},
                "schedule": {"only_wifi": False},
            },
            current,
        )
        self.assertEqual(updated["interface"]["language"], "pt-BR")
        self.assertEqual(updated["vehicle"]["device_token"], "device-token")
        self.assertEqual(updated["vehicle"]["model_name"], "Generic EV")
        self.assertFalse(updated["schedule"]["only_wifi"])

        updated_again = validate_settings(
            {"vehicle": {"name": "Second name"}},
            updated,
        )
        self.assertEqual(updated_again["interface"]["language"], "pt-BR")

    def test_retention_partial_updates_preserve_other_rules(self) -> None:
        current = validate_settings(
            {
                "retention": {
                    "categories": {
                        "recordings": {
                            "enabled": True,
                            "value": 48,
                            "unit": "hours",
                            "keep_latest_enabled": True,
                            "keep_latest_count": 12,
                        }
                    },
                    "storage_limit": {
                        "enabled": True,
                        "max_bytes": 50_000_000_000,
                    },
                }
            }
        )

        updated = validate_settings(
            {
                "retention": {
                    "categories": {
                        "trips": {"enabled": True, "value": 90},
                        "recordings": {"keep_latest_count": 20},
                    }
                }
            },
            current,
        )

        self.assertEqual(
            updated["retention"]["categories"]["recordings"],
            {
                "enabled": True,
                "value": 48,
                "unit": "hours",
                "keep_latest_enabled": True,
                "keep_latest_count": 20,
            },
        )
        self.assertEqual(
            updated["retention"]["categories"]["trips"],
            {
                "enabled": True,
                "value": 90,
                "unit": "days",
                "keep_latest_enabled": False,
                "keep_latest_count": 1,
            },
        )
        self.assertEqual(
            updated["retention"]["storage_limit"],
            {"enabled": True, "max_bytes": 50_000_000_000},
        )

    def test_legacy_settings_gain_retention_defaults(self) -> None:
        legacy = default_settings()
        legacy.pop("retention")

        normalized = validate_settings(legacy)
        partially_updated = validate_settings(
            {"vehicle": {"name": "Legacy EV"}},
            legacy,
        )

        for settings in (normalized, partially_updated):
            self.assertEqual(set(settings["retention"]["categories"]), set(CATEGORIES))
            self.assertEqual(
                settings["retention"]["storage_limit"],
                {"enabled": False, "max_bytes": 0},
            )

    def test_retention_rejects_invalid_category_rules(self) -> None:
        invalid_updates = (
            {"recordings": {"enabled": 1}},
            {"recordings": {"value": 0}},
            {"recordings": {"value": 1_000_001}},
            {"recordings": {"value": "30"}},
            {"recordings": {"unit": "weeks"}},
            {"recordings": {"keep_latest_enabled": 1}},
            {"recordings": {"keep_latest_count": 0}},
            {"recordings": {"keep_latest_count": 1_000_001}},
            {"recordings": {"keep_latest_count": "5"}},
            {"unknown": {"enabled": False}},
        )
        for categories in invalid_updates:
            with self.subTest(categories=categories):
                with self.assertRaises(SettingsError):
                    validate_settings({"retention": {"categories": categories}})

    def test_retention_rejects_invalid_storage_limits(self) -> None:
        for storage_limit in (
            {"enabled": 1},
            {"enabled": True, "max_bytes": 0},
            {"max_bytes": -1},
            {"max_bytes": 1 << 63},
            {"max_bytes": "1024"},
            {"max_bytes": True},
        ):
            with self.subTest(storage_limit=storage_limit):
                with self.assertRaises(SettingsError):
                    validate_settings(
                        {"retention": {"storage_limit": storage_limit}}
                    )

    def test_retention_accepts_boundary_values(self) -> None:
        settings = validate_settings(
            {
                "retention": {
                    "categories": {
                        "recordings": {
                            "enabled": True,
                            "value": 1_000_000,
                            "unit": "minutes",
                            "keep_latest_enabled": True,
                            "keep_latest_count": 1_000_000,
                        }
                    },
                    "storage_limit": {
                        "enabled": True,
                        "max_bytes": (1 << 63) - 1,
                    },
                }
            }
        )
        rule = settings["retention"]["categories"]["recordings"]
        self.assertEqual(rule["value"], 1_000_000)
        self.assertEqual(rule["unit"], "minutes")
        self.assertEqual(rule["keep_latest_count"], 1_000_000)
        self.assertEqual(
            settings["retention"]["storage_limit"]["max_bytes"],
            (1 << 63) - 1,
        )

    def test_interface_language_rejects_unsupported_values(self) -> None:
        for language in ("pt", "en-US", "", None, 123):
            with self.subTest(language=language):
                with self.assertRaises(SettingsError):
                    validate_settings({"interface": {"language": language}})

    def test_destination_rejects_path_traversal(self) -> None:
        with self.assertRaises(SettingsError):
            validate_settings({"destination": {"subdirectory": "../private"}})

    def test_vehicle_origin_uses_effective_port(self) -> None:
        self.assertEqual(
            base_url_origin("https://vehicle.example"),
            base_url_origin("https://VEHICLE.example:443/overdrive"),
        )
        self.assertNotEqual(
            base_url_origin("https://vehicle.example"),
            base_url_origin("http://vehicle.example"),
        )
        with self.assertRaises(SettingsError):
            base_url_origin("https://vehicle.example:99999")
        with self.assertRaises(SettingsError):
            base_url_origin("https://vehicle.example:0")
        with self.assertRaises(SettingsError):
            base_url_origin("https://vehicle.example/has space")

    def test_discovered_profile_preserves_manual_vehicle_fields(self) -> None:
        changes = discovered_vehicle_changes(
            {
                "model_id": "manual-id",
                "model_name": "Manual model",
                "color": "#ffffff",
                "drive_side": "lhd",
            },
            {
                "device_id": "device-new",
                "app_version": "1.2.3",
                "locale": "en-US",
                "distance_unit": "km",
                "recording_layout": "dashcam",
                "surveillance_layout": "standard",
                "model_id": "detected-id",
                "model_name": "Detected model",
                "color": "#000000",
                "drive_side": "rhd",
            },
        )
        self.assertEqual(changes["device_id"], "device-new")
        self.assertEqual(changes["app_version"], "1.2.3")
        self.assertEqual(changes["locale"], "en-US")
        self.assertEqual(changes["distance_unit"], "km")
        self.assertEqual(changes["recording_layout"], "dashcam")
        self.assertEqual(changes["surveillance_layout"], "standard")
        self.assertNotIn("model_id", changes)
        self.assertNotIn("model_name", changes)
        self.assertNotIn("color", changes)
        self.assertNotIn("drive_side", changes)

    def test_camera_layout_rejects_unsupported_values(self) -> None:
        with self.assertRaises(SettingsError):
            validate_settings({"vehicle": {"recording_layout": "vertical"}})
        with self.assertRaises(SettingsError):
            validate_settings({"vehicle": {"surveillance_layout": "single"}})

    def test_partial_discovery_does_not_clear_known_runtime_fields(self) -> None:
        changes = discovered_vehicle_changes(
            {
                "device_id": "known-device",
                "app_version": "1.0.0",
                "locale": "en-US",
                "distance_unit": "km",
            },
            {
                "device_id": "unknown",
                "app_version": "",
                "locale": None,
                "distance_unit": "",
            },
        )
        self.assertEqual(changes, {})

    def test_wifi_policy_can_be_disabled_or_restricted_by_ssid(self) -> None:
        settings = validate_settings(default_settings())
        settings["schedule"]["only_wifi"] = False
        allowed, _ = wifi_policy(settings, {"type": "cellular"})
        self.assertTrue(allowed)

        settings["schedule"]["only_wifi"] = True
        settings["schedule"]["allowed_ssids"] = ["Garage"]
        allowed, _ = wifi_policy(settings, {"type": "wifi", "ssid": "Home"})
        self.assertFalse(allowed)
        allowed, _ = wifi_policy(settings, {"type": "wifi", "ssid": "Garage"})
        self.assertTrue(allowed)

    def test_interval_schedule_uses_last_scheduled_run(self) -> None:
        settings = validate_settings(default_settings())
        settings["schedule"].update(
            {
                "enabled": True,
                "mode": "interval",
                "interval_value": 2,
                "interval_unit": "hours",
            }
        )
        last = datetime(2026, 7, 16, 10, 0, tzinfo=timezone.utc)
        due = next_run_at(
            settings,
            last,
            datetime(2026, 7, 16, 10, 30, tzinfo=timezone.utc),
        )
        self.assertEqual(
            due,
            datetime(2026, 7, 16, 12, 0, tzinfo=timezone.utc),
        )

    def test_daily_schedule_catches_up_after_a_missed_slot(self) -> None:
        settings = validate_settings(default_settings())
        settings["schedule"].update(
            {
                "enabled": True,
                "mode": "daily",
                "daily_time": "02:00",
                "timezone": "UTC",
            }
        )
        now = datetime(2026, 7, 16, 3, 0, tzinfo=timezone.utc)
        due = next_run_at(
            settings,
            datetime(2026, 7, 15, 2, 0, tzinfo=timezone.utc),
            now,
        )
        self.assertEqual(due, now)

    def test_daily_schedule_keeps_todays_slot_after_an_earlier_run(self) -> None:
        settings = validate_settings(default_settings())
        settings["schedule"].update(
            {
                "enabled": True,
                "mode": "daily",
                "daily_time": "23:58",
                "timezone": "UTC",
            }
        )
        due = next_run_at(
            settings,
            datetime(2026, 7, 16, 0, 3, tzinfo=timezone.utc),
            datetime(2026, 7, 16, 0, 10, tzinfo=timezone.utc),
        )
        self.assertEqual(
            due,
            datetime(2026, 7, 16, 23, 58, tzinfo=timezone.utc),
        )

    def test_daily_schedule_advances_after_todays_slot_ran(self) -> None:
        settings = validate_settings(default_settings())
        settings["schedule"].update(
            {
                "enabled": True,
                "mode": "daily",
                "daily_time": "02:00",
                "timezone": "UTC",
            }
        )
        due = next_run_at(
            settings,
            datetime(2026, 7, 16, 2, 0, tzinfo=timezone.utc),
            datetime(2026, 7, 16, 3, 0, tzinfo=timezone.utc),
        )
        self.assertEqual(
            due,
            datetime(2026, 7, 17, 2, 0, tzinfo=timezone.utc),
        )


if __name__ == "__main__":
    unittest.main()
