"""Regression tests with the actual HA ConfigFlow superclass."""
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from custom_components.media_activity_tracker.config_flow import ConfigFlow


class ConfigFlowTests(unittest.IsolatedAsyncioTestCase):
    async def test_select_player_preserves_reserved_source(self):
        flow = ConfigFlow()
        flow.context = {"source": "user"}
        flow.hass = MagicMock()
        flow.flow_id = "test-flow"
        with (
            patch("custom_components.media_activity_tracker.config_flow.entity_ref", return_value="registry-id"),
            patch.object(flow, "async_set_unique_id", new_callable=AsyncMock) as set_id,
            patch.object(flow, "_abort_if_unique_id_configured"),
        ):
            result = await flow.async_step_user({"name": "Test TV", "entity": "media_player.test"})
        set_id.assert_awaited_once_with("registry-id")
        self.assertEqual(flow.source, "user")
        self.assertEqual(result["step_id"], "settings")
        with patch.object(flow, "async_create_entry", return_value={"type": "create_entry"}) as create:
            await flow.async_step_settings({"mode": "playing", "logic": "and", "condition_entities": []})
        create.assert_called_once_with(title="Test TV", data={"source": "registry-id", "mode": "playing", "logic": "and", "conditions": []})

    async def test_condition_step(self):
        flow = ConfigFlow()
        flow.context = {"source": "user"}
        flow.hass = MagicMock()
        flow.flow_id = "test-flow"
        flow._media_source_ref = "registry-id"
        flow._tracker_name = "Test TV"
        result = await flow.async_step_settings({"mode": "playing", "logic": "and", "condition_entities": ["binary_sensor.tv"]})
        self.assertEqual(result["step_id"], "condition")
        with (
            patch("custom_components.media_activity_tracker.config_flow.entity_ref", return_value="condition-id"),
            patch.object(flow, "async_create_entry", return_value={"type": "create_entry"}) as create,
        ):
            await flow.async_step_condition({"operator": "equals", "value": "on"})
        create.assert_called_once_with(title="Test TV", data={"source": "registry-id", "mode": "playing", "logic": "and", "conditions": [{"entity": "condition-id", "operator": "equals", "value": "on"}]})

    async def test_session_retention_form(self):
        flow = ConfigFlow()
        flow.context = {"source": "user"}
        flow.hass = MagicMock()
        flow.flow_id = "test-flow"
        flow._media_source_ref = "registry-id"
        flow._tracker_name = "Test TV"
        form = await flow.async_step_settings()
        data = {"mode": "playing", "logic": "and", "retention_days": 365}
        self.assertEqual(form["data_schema"](data)["retention_days"], 365)
        import voluptuous as vol
        for invalid in (0, 3651):
            with self.assertRaises(vol.Invalid):
                form["data_schema"]({**data, "retention_days": invalid})
        with patch.object(flow, "async_create_entry", return_value={"type": "create_entry"}) as create:
            await flow.async_step_settings(data)
        self.assertEqual(create.call_args.kwargs["data"]["retention_days"], 365)


class ApplicationSettingsTests(unittest.TestCase):
    def test_legacy_and_structured_options(self):
        from custom_components.media_activity_tracker.config_values import app_list, aliases, valid_application_settings
        self.assertEqual(app_list("Netflix, YouTube"),["Netflix","YouTube"])
        self.assertEqual(aliases("id:12=Netflix"),{"id:12":"Netflix"})
        self.assertEqual(aliases([{"key":"id:12","label":"Netflix, TV"}]),{"id:12":"Netflix, TV"})
        self.assertFalse(valid_application_settings({"aliases":[{"key":"x","label":"A"},{"key":"X","label":"B"}]}))
