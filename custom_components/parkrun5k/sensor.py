import logging
from datetime import datetime
from typing import Any, Dict, Optional

from homeassistant.components.sensor import (
    SensorEntity,
    SensorStateClass,
    SensorDeviceClass,
)
from homeassistant.util import dt as dt_util
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import (
    CoordinatorEntity,
)

from . import DOMAIN, ParkrunDataUpdateCoordinator
from .local_data import get_event_name
from .records import rolling_records, refresh_locations

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Parkrun5k sensors from a config entry."""
    coordinator = hass.data[DOMAIN][config_entry.entry_id]
    
    sensors = [
        ParkrunCategorySensor(coordinator),
        ParkrunMilestoneSensor(coordinator),
        ParkrunLatestRunSensor(coordinator),
        ParkrunTotalRunsSensor(coordinator),
        ParkrunLocationsSensor(coordinator),
        ParkrunActivityLocationsSensor(coordinator, "volunteer"),
        ParkrunActivityLocationsSensor(coordinator, "visited"),
        ParkrunVolunteerSensor(coordinator),
        ParkrunBestAgeGradeSensor(coordinator),
        ParkrunPersonalBestSensor(coordinator),
        ParkrunYearBestSensor(coordinator),
        ParkrunRollingSensor(coordinator, "time"),
        ParkrunRollingSensor(coordinator, "age_grade"),
    ]
    
    async_add_entities(sensors)

class ParkrunSensor(CoordinatorEntity, SensorEntity):
    """Base class for all Parkrun sensors."""

    def __init__(self, coordinator: ParkrunDataUpdateCoordinator):
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._attr_has_entity_name = True
        self.runner_name = coordinator.runner_name
        self.entry_id = coordinator.entry_id
        self.barcode = coordinator.barcode
    
    @property
    def device_info(self):
        """Return device information about this entity."""
        return {
            "identifiers": {(DOMAIN, self.entry_id)},
            "name": f"Parkrun5k {self.runner_name}",
            "manufacturer": "Parkrun",
            "model": f"Barcode A{self.barcode}",
            "sw_version": "3.0.0",
        }
        
    @property
    def available(self) -> bool:
        """Return if entity is available."""
        return self.coordinator.last_update_success and self.coordinator.data is not None

class ParkrunCategorySensor(ParkrunSensor):
    """Sensor for Parkrun age category."""

    def __init__(self, coordinator):
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._attr_name = "Category"
        self._attr_unique_id = f"parkrun5k_{coordinator.entry_id}_category"
        self._attr_icon = "mdi:run-fast"
    
    @property
    def native_value(self):
        """Return the state of the sensor."""
        if self.coordinator.data:
            return self.coordinator.data.get("latest_category", "Unknown")
        return "Unknown"

class ParkrunMilestoneSensor(ParkrunSensor):
    """Sensor for Parkrun latest milestone."""

    def __init__(self, coordinator):
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._attr_name = "Latest Milestone"
        self._attr_unique_id = f"parkrun5k_{coordinator.entry_id}_milestone"
        self._attr_icon = "mdi:medal"
        self._attr_native_unit_of_measurement = "runs"
        self._attr_state_class = SensorStateClass.MEASUREMENT
    
    @property
    def native_value(self):
        """Return the state of the sensor."""
        if self.coordinator.data:
            return self.coordinator.data.get("latest_milestone", 0)
        return 0


class ParkrunLatestRunSensor(ParkrunSensor):
    """Sensor for details of the most recent run."""

    def __init__(self, coordinator):
        super().__init__(coordinator)
        self._attr_name = "Latest Run"
        self._attr_unique_id = f"parkrun5k_{coordinator.entry_id}_latest_run"
        self._attr_icon = "mdi:calendar"
        self._attr_device_class = SensorDeviceClass.TIMESTAMP

    @property
    def native_value(self):
        if not self.coordinator.data:
            return None

        runs = self.coordinator.data.get("runs")
        if not runs:
            return None

        date_str = runs[0].get("date")
        if not date_str:
            return None

        try:
            dt_obj = dt_util.parse_datetime(date_str)
            if dt_obj is None:
                return None
            dt_obj = dt_obj.replace(hour=9, minute=0, second=0, microsecond=0)
            if dt_obj.tzinfo is None:
                dt_obj = dt_obj.replace(tzinfo=dt_util.UTC)
            return dt_obj
        except (ValueError, TypeError):
            return None

    @property
    def extra_state_attributes(self):
        if not self.coordinator.data:
            return {}

        runs = self.coordinator.data.get("runs")
        if not runs:
            return {}

        run = runs[0]
        attributes = {
            "time": run.get("time"),
            "location": run.get("eventName") or get_event_name(run.get("eventId")),
            "source": run.get("source", "legacy"),
            "event_number": run.get("runNumber"),
        }

        if run.get("ageGrade") is not None:
            attributes["age_grade"] = run.get("ageGrade")

        field_map = {
            "venuePB": "venue_pb",
            "yearBest": "year_best",
            "venueRuns": "venue_runs",
            "position": "position",
            "genderPosition": "gender_position",
            "ageGradePosition": "age_grade_position",
            "ageCategoryPosition": "age_category_position",
            "totalAthletes": "total_runners",
        }

        for key, attr in field_map.items():
            if run.get(key) is not None:
                attributes[attr] = run.get(key)

        return attributes

class ParkrunTotalRunsSensor(ParkrunSensor):
    """Sensor for total Parkruns."""

    def __init__(self, coordinator):
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._attr_name = "Total Runs"
        self._attr_unique_id = f"parkrun5k_{coordinator.entry_id}_total_runs"
        self._attr_icon = "mdi:counter"
        self._attr_native_unit_of_measurement = "runs"
        self._attr_state_class = SensorStateClass.MEASUREMENT
    
    @property
    def native_value(self):
        """Return the state of the sensor."""
        if self.coordinator.data:
            return self.coordinator.data.get("total_runs")
        return 0
        
    @property
    def extra_state_attributes(self):
        """Return additional attributes about recent runs."""
        if not self.coordinator.data:
            return {}
            
        attributes = {"history_complete": self.coordinator.data.get("history_complete", False),
                      "source": self.coordinator.data.get("result_source", "legacy")}
        recent_runs = self.coordinator.data.get("runs", [])
        
        if recent_runs:
            attributes["recent_runs"] = []
            for i, run in enumerate(recent_runs[:5]):  # Get the 5 most recent runs
                event_id = run.get("eventId")
                event_name = run.get("eventName") or get_event_name(event_id)
                
                attributes["recent_runs"].append({
                    "date": run.get("date"),
                    "time": run.get("time"),
                    "position": run.get("position"),
                    "event_id": event_id,
                    "event_name": event_name,
                    "total_runners": run.get("totalAthletes")
                })
        
        return attributes

class ParkrunLocationsSensor(ParkrunSensor):
    """Sensor for number of unique locations."""

    def __init__(self, coordinator):
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._attr_name = "Unique Locations"
        self._attr_unique_id = f"parkrun5k_{coordinator.entry_id}_locations"
        self._attr_icon = "mdi:map-marker-multiple"
        self._attr_native_unit_of_measurement = "locations"
        self._attr_state_class = SensorStateClass.MEASUREMENT
    
    @property
    def native_value(self):
        """Return the state of the sensor."""
        if self.coordinator.data:
            return self.coordinator.data.get("unique_locations")
        return 0

    @property
    def extra_state_attributes(self):
        data = self.coordinator.data or {}
        details = data.get("location_details", [])
        return {"locations": [item["location"] for item in details],
                "location_details": details,
                "known_location_count": len(details),
                "history_complete": data.get("history_complete", False)}

class ParkrunVolunteerSensor(ParkrunSensor):
    """Sensor for volunteer count."""

    def __init__(self, coordinator):
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._attr_name = "Volunteer Count"
        self._attr_unique_id = f"parkrun5k_{coordinator.entry_id}_volunteers"
        self._attr_icon = "mdi:account-group"
        self._attr_native_unit_of_measurement = "times"
        self._attr_state_class = SensorStateClass.MEASUREMENT
    
    @property
    def native_value(self):
        """Return the state of the sensor."""
        if self.coordinator.data:
            return self.coordinator.data.get("volunteer_count")
        return 0
    
    @property
    def extra_state_attributes(self):
        """Return additional attributes about volunteering."""
        if not self.coordinator.data:
            return {}
            
        attributes = {"reported_as_of": self.coordinator.data.get("volunteer_report_date"),
                      "history_complete": self.coordinator.data.get("volunteer_history_complete", False)}
        volunteer_roles = self.coordinator.data.get("volunteer_roles", [])
        
        if volunteer_roles:
            attributes["roles"] = {}
            for role in volunteer_roles:
                attributes["roles"][role["name"]] = role["count"]
        
        return attributes

class ParkrunPersonalBestSensor(ParkrunSensor):
    """Sensor for personal best time."""

    def __init__(self, coordinator):
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._attr_name = "Personal Best"
        self._attr_unique_id = f"parkrun5k_{coordinator.entry_id}_pb"
        self._attr_icon = "mdi:timer-outline"
    
    @property
    def native_value(self):
        """Return the state of the sensor."""
        if self.coordinator.data:
            return self.coordinator.data.get("personal_best", "Unknown")
        return "Unknown"
    
    @property
    def extra_state_attributes(self):
        """Return additional attributes about the PB."""
        if not self.coordinator.data:
            return {}
            
        attributes = {
            "date": self.coordinator.data.get("pb_date"),
            "location": self.coordinator.data.get("pb_location"),
            "event_id": self.coordinator.data.get("pb_event_id"),
            "record_source": self.coordinator.data.get("pb_source"),
            "history_complete": self.coordinator.data.get("history_complete", False),
        }
        
        return attributes


class ParkrunBestAgeGradeSensor(ParkrunSensor):
    """Sensor for best age grade."""

    def __init__(self, coordinator):
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._attr_name = "Best Age Grade"
        self._attr_unique_id = f"parkrun5k_{coordinator.entry_id}_best_age_grade"
        self._attr_icon = "mdi:calendar-star"
        self._attr_native_unit_of_measurement = "%"
        self._attr_state_class = SensorStateClass.MEASUREMENT

    @property
    def native_value(self):
        """Return the state of the sensor."""
        if self.coordinator.data:
            value = self.coordinator.data.get("best_age_grade")
            if value is not None:
                return round(value, 2)
        return None

    @property
    def extra_state_attributes(self):
        """Return details about the best age grade."""
        if not self.coordinator.data:
            return {}

        return {
            "date": self.coordinator.data.get("bag_date"),
            "location": self.coordinator.data.get("bag_location"),
            "event_id": self.coordinator.data.get("bag_event_id"),
            "record_source": self.coordinator.data.get("bag_source"),
            "history_complete": self.coordinator.data.get("history_complete", False),
        }



class ParkrunYearBestSensor(ParkrunSensor):
    """Best known result in the current local calendar year."""

    def __init__(self, coordinator):
        super().__init__(coordinator)
        self._attr_name = "Best Time This Year"
        self._attr_unique_id = f"parkrun5k_{coordinator.entry_id}_year_best"
        self._attr_icon = "mdi:calendar-clock"

    async def async_added_to_hass(self):
        await super().async_added_to_hass()
        from homeassistant.helpers.event import async_track_time_change
        @callback
        def midnight_update(now):
            self.async_write_ha_state()

        self.async_on_remove(async_track_time_change(
            self.hass, midnight_update, hour=0, minute=0, second=0,
        ))

    @property
    def native_value(self):
        data = self.coordinator.data or {}
        return data.get("year_bests", {}).get(str(dt_util.now().year))

    @property
    def extra_state_attributes(self):
        return {"year": dt_util.now().year}


class ParkrunRollingSensor(ParkrunSensor):
    """Best dated performance within the preceding twelve calendar months."""

    def __init__(self, coordinator, kind):
        super().__init__(coordinator)
        self.kind = kind
        self._attr_name = "Best Time Last 12 Months" if kind == "time" else "Best Age Grade Last 12 Months"
        self._attr_unique_id = f"parkrun5k_{coordinator.entry_id}_rolling_12m_{kind}"
        self._attr_icon = "mdi:calendar-clock"
        if kind == "age_grade":
            self._attr_native_unit_of_measurement = "%"
            self._attr_state_class = SensorStateClass.MEASUREMENT

    async def async_added_to_hass(self):
        await super().async_added_to_hass()
        from homeassistant.helpers.event import async_track_time_change
        @callback
        def midnight_update(now):
            self.async_write_ha_state()

        self.async_on_remove(async_track_time_change(
            self.hass, midnight_update, hour=0, minute=0, second=0,
        ))

    def _records(self):
        return rolling_records(self.coordinator.data or {}, dt_util.now().date(), get_event_name)

    @property
    def native_value(self):
        return self._records()[self.kind]["value"]

    @property
    def extra_state_attributes(self):
        records = self._records()
        attributes = {k: v for k, v in records[self.kind].items() if k != "value"}
        attributes.update({k: records[k] for k in ("window_start_exclusive", "window_end", "known_results_in_window")})
        attributes["history_complete"] = (self.coordinator.data or {}).get("history_complete", False)
        return attributes


class ParkrunActivityLocationsSensor(ParkrunSensor):
    """Known volunteering venues or the union of running and volunteering venues."""

    def __init__(self, coordinator, kind):
        super().__init__(coordinator)
        self.kind = kind
        self._attr_name = "Volunteer Locations" if kind == "volunteer" else "Visited Locations"
        self._attr_unique_id = f"parkrun5k_{coordinator.entry_id}_{kind}_locations"
        self._attr_icon = "mdi:map-marker-multiple"
        self._attr_native_unit_of_measurement = "locations"
        self._attr_state_class = SensorStateClass.MEASUREMENT

    def _locations(self):
        from copy import deepcopy
        return refresh_locations(deepcopy(self.coordinator.data or {}), get_event_name)

    @property
    def native_value(self):
        return len(self._locations().get(f"{self.kind}_location_details", []))

    @property
    def extra_state_attributes(self):
        data = self._locations()
        details = data[f"{self.kind}_location_details"]
        complete = data.get("volunteer_history_complete", False)
        if self.kind == "visited":
            complete = complete and data.get("history_complete", False)
        return {"locations": [item["location"] for item in details], "location_details": details,
                "history_complete": complete, "count_basis": "known venues"}
