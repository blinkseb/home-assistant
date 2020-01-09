"""Config flow to configure Xiaomi Aqara."""
import asyncio
from typing import Dict, Optional
from urllib.parse import urlparse

import async_timeout
import voluptuous as vol
from xiaomi_gateway import XiaomiGateway, XiaomiGatewayDiscovery

from homeassistant import config_entries, core
from homeassistant.helpers import aiohttp_client

from . import _LOGGER, DOMAIN  # pylint: disable=unused-import

HUE_MANUFACTURERURL = "http://www.philips.com"
HUE_IGNORED_BRIDGE_NAMES = ["Home Assistant Bridge", "Espalexa"]


class AqaraFlowHandler(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a Aqara config flow."""

    VERSION = 1
    CONNECTION_CLASS = config_entries.CONN_CLASS_LOCAL_POLL

    # pylint: disable=no-member # https://github.com/PyCQA/pylint/issues/3167

    def __init__(self):
        """Initialize the Hue flow."""
        self.gateway: Optional[XiaomiGateway] = None
        self.discovered_gateways: Optional[Dict[str, XiaomiGateway]] = None

    async def async_step_user(self, user_input=None):
        """Handle a flow initialized by the user."""
        # This is for backwards compatibility.
        return await self.async_step_init(user_input)

    @core.callback
    def _async_get_gateway(self, host: str, bridge_id: Optional[str] = None):
        """Return a bridge object."""
        if bridge_id is not None:
            bridge_id = normalize_bridge_id(bridge_id)

        return aiohue.Bridge(
            host,
            websession=aiohttp_client.async_get_clientsession(self.hass),
            bridge_id=bridge_id,
        )

    async def async_step_init(self, user_input=None):
        """Handle a flow start."""

        # Check if it's an answer to the default gateway choice
        if (
            user_input is not None
            and self.discovered_gateways is not None
            # pylint: disable=unsupported-membership-test
            and user_input["id"] in self.discovered_gateways
        ):
            # pylint: disable=unsubscriptable-object
            self.gateway = self.discovered_gateways[user_input["id"]]
            await self.async_set_unique_id(self.gateway.sid, raise_on_progress=False)
            # We pass user input to link so it will attempt to link right away
            return await self.async_step_link({})

        _LOGGER.info(user_input)

        _LOGGER.debug("starting discovery of Aqara gateway")

        gateway_discovery = XiaomiGatewayDiscovery(
            self.hass.add_job, gateways_config=[], interface="any"
        )

        _LOGGER.info(gateway_discovery)

        gateway_discovery.discover_gateways()

        gateways = gateway_discovery.gateways.values()

        gateways = [
            XiaomiGateway(
                "192.168.1.100",
                "80",
                "0123456789abcdef",
                "keykeykey",
                5,
                "any",
                "1.2.3",
            )
        ]

        if not gateways:
            _LOGGER.info("no gateways discovered")
            return self.async_abort(reason="no_gateways")

        # Find already configured hosts
        already_configured = self._async_current_ids(False)
        gateways = [
            gateway for gateway in gateways if gateway.sid not in already_configured
        ]

        if not gateways:
            return self.async_abort(reason="all_configured")

        if len(gateways) == 1:
            self.gateway = gateways[0]
            await self.async_set_unique_id(self.gateway.sid, raise_on_progress=False)
            return await self.async_step_key()

        self.discovered_gateways = {gateway.sid: gateway for gateway in gateways}

        # Ask the user to choose a default gateway
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Required("id"): vol.In(
                        {gateway.sid: gateway.ip_adress for gateway in gateways}
                    )
                }
            ),
        )

    async def async_step_key(self, user_input=None):
        """Ask the user for the gateway key.
        """
        if user_input is None:
            return self.async_show_form(
                step_id="key", data_schema=vol.Schema({vol.Required("key"): str})
            )

        gateway = self.gateway
        assert gateway is not None

        return self.async_create_entry(
            title="Xiaomi Aqara",
            data={
                "ip": gateway.ip_adress,
                "port": gateway.port,
                "sid": gateway.sid,
                "key": gateway.key,
                "discovery_retries": gateway._discovery_retries,
                "interface": gateway._interface,
            },
        )

    async def async_step_import(self, import_info):
        """Import a new bridge as a config entry.

        This flow is triggered by `async_setup` for both configured and
        discovered bridges. Triggered for any bridge that does not have a
        config entry yet (based on host).

        This flow is also triggered by `async_step_discovery`.
        """
        # Check if host exists, abort if so.
        if any(
            import_info["sid"] == entry.data["sid"]
            for entry in self._async_current_entries()
        ):
            return self.async_abort(reason="already_configured")

        # self.gateway = self._async_get_bridge(import_info["host"])
        return await self.async_step_key()
