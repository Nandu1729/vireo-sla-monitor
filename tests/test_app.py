import datetime as dt
import unittest

import app


class ShiftTests(unittest.TestCase):
    def test_shift_boundaries(self):
        self.assertEqual(app.shift_for_time(dt.datetime(2026, 1, 1, 5, 59)), "Night")
        self.assertEqual(app.shift_for_time(dt.datetime(2026, 1, 1, 6, 0)), "Morning")
        self.assertEqual(app.shift_for_time(dt.datetime(2026, 1, 1, 13, 59)), "Morning")
        self.assertEqual(app.shift_for_time(dt.datetime(2026, 1, 1, 14, 0)), "Day")
        self.assertEqual(app.shift_for_time(dt.datetime(2026, 1, 1, 21, 59)), "Day")
        self.assertEqual(app.shift_for_time(dt.datetime(2026, 1, 1, 22, 0)), "Night")


class DedupeTests(unittest.TestCase):
    def test_current_helpdesk_copy_wins(self):
        legacy = {
            "ticket_id": "TK-1",
            "source_system": "legacy_fd",
            "csat_score": "0",
            "resolved_at": "2025-01-01 00:20",
        }
        current = {
            "ticket_id": "TK-1",
            "source_system": "helpdesk",
            "csat_score": "",
            "resolved_at": "2025-01-01 00:20",
        }
        rows, quality = app.deduplicate([legacy, current])
        self.assertEqual(rows[0]["source_system"], "helpdesk")
        self.assertEqual(quality["duplicate_rows_removed"], 1)
        self.assertEqual(quality["duplicate_groups_with_material_conflicts"], 0)


class CalculationTests(unittest.TestCase):
    def setUp(self):
        self.config = {
            "timezone_offset_minutes": 330,
            "sla_minutes": {"chat": 15, "voice": 120, "social": 240, "email": 480},
        }
        self.agent = {
            "agent_id": "A1",
            "name": "Test Agent",
            "site": "Indore",
            "team": "Chat Frontline",
            "shift": "Morning",
            "tier": "1",
            "from_date": "2025-01-01",
            "to_date": "",
        }

    def ticket(self, ticket_id, response_at):
        return {
            "ticket_id": ticket_id,
            "created_at": "2026-01-01 00:30",
            "first_response_at": response_at,
            "resolved_at": "2026-01-01 01:00",
            "status": "resolved",
            "channel": "chat",
            "agent_id": "A1",
            "source_system": "helpdesk",
        }

    def test_exact_threshold_is_not_a_breach(self):
        records, quality = app.build_records(
            [self.ticket("TK-1", "2026-01-01 00:45")], [self.agent], self.config
        )
        self.assertFalse(records[0]["breach"])
        self.assertEqual(records[0]["response_minutes"], 15)
        self.assertEqual(quality["roster_date_unmatched_or_ambiguous"], 0)

    def test_one_minute_late_is_a_breach_and_utc_becomes_ist(self):
        records, _ = app.build_records(
            [self.ticket("TK-2", "2026-01-01 00:46")], [self.agent], self.config
        )
        self.assertTrue(records[0]["breach"])
        self.assertEqual(records[0]["created_ist"].time(), dt.time(6, 0))
        self.assertEqual(records[0]["creation_shift"], "Morning")


class ModelTests(unittest.TestCase):
    def test_change_point_detector_finds_known_break(self):
        start = dt.date(2026, 1, 1)
        records = []
        for day in range(80):
            current = start + dt.timedelta(days=day)
            for ticket in range(10):
                before_break = day < 40
                breach = ticket == 0 if before_break else ticket < 8
                records.append(
                    {
                        "created_ist": dt.datetime.combine(current, dt.time(9)),
                        "breach": breach,
                    }
                )
        result = app.detect_change_point(records, min_segment_days=20)
        self.assertIsNotNone(result)
        self.assertEqual(result["split_date"], start + dt.timedelta(days=40))
        self.assertAlmostEqual(result["before_rate"], 0.1)
        self.assertAlmostEqual(result["after_rate"], 0.8)


if __name__ == "__main__":
    unittest.main()
