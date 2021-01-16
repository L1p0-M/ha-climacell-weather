from datetime import datetime
from datetime import timedelta
from datetime import time

import logging
import re

import json
import requests
import socket

from homeassistant.util import Throttle

_LOGGER = logging.getLogger(__name__)

ATTR_SERVICE_COUNTER = "service_counter"
_HOSTNAME = 'data.climacell.co'
_ENDPOINT = 'https://' + _HOSTNAME + '/v4'

class ClimacellTimelineDataProvider:

    def __init__(self, api_key, latitude, longitude, interval, units, fields, start_time, timesteps, observations, exceptions=None, inc_counter=1):
        self.__name = "timeline"
        self.__update_timestamp = datetime.today()
        self.__service_counter = 0
        self.__inc_counter = inc_counter

        self.__interval = interval
        self.__exceptions = exceptions

        self.__throttle_user_update = Throttle(interval)(self._user_update)
        self.__throttle_update = Throttle(timedelta(seconds=300))(self.__update_controller)

        self.__api_key = api_key
        self.__latitude = latitude
        self.__longitude = longitude
        self.__fields = ','.join(fields)
        self.__observations = observations
        self.__start_time = start_time
        self.__timesteps = timesteps
        self.__units = units

        """Initialize the data object."""
        self.data = None

        self.__headers = {
            'Content-Type': 'application/json',
            'apikey': api_key,
        }
        
        self._params = 'location=' + str(latitude) + ',' + str(longitude)  + '&units=' + self.__units + '&timesteps=' + self.__timesteps

        _LOGGER.debug("ClimacellTimelineDataProvider initializated for: %s.", self.__fields)

    @staticmethod
    def __is_between(time, time_range):
        if time_range[1] < time_range[0]:
            return time >= time_range[0] or time <= time_range[1]
        return time_range[0] <= time <= time_range[1]

    def __reset_service_counter(self):
        self.__update_timestamp = datetime.today()
        self.__service_counter = 0

    def __inc_service_counter(self, inc_counter=None):
        if self.__update_timestamp.date() == datetime.today().date():
            incr = (self.__inc_counter if inc_counter is None else inc_counter)
            self.__service_counter = self.__service_counter + incr
            _LOGGER.debug("Service '%s' usage: %s with incr: %s (def. %s)",
                          self.__name, self.__service_counter, incr, self.__inc_counter)
        else:
            self.__reset_service_counter()
            _LOGGER.debug("Service '%s' usage resetted: %s", self.__name, self.__service_counter)

    @property
    def service_counter(self):
        return self.__service_counter

    def _set_service_counter(self, val):
        self.__service_counter = val

    @property
    def service_counter_update_timestamp(self):
        return self.__update_timestamp

    def _set_service_counter_update_timestamp(self, val):
        self.__update_timestamp = val

    def retrieve_update(self):
        self.__throttle_update()

    def __update_controller(self):
        """
        """
        now = datetime.now()
        hourminute = "" + str(now.hour) + ":" + str(now.minute)

        update = True

        if self.__exceptions is not None:
            for key, value in self.__exceptions[0].items():
                if self.__is_between(hourminute, value):
                    update = False

        if update:
            updt_state = self.__throttle_user_update()
            if updt_state:
                self.__inc_service_counter()

    def _user_update(self):
        """Get the latest data from climacell"""

        if self.__fields is not '':
            querystring = self._params
            querystring += '&fields=' + self.__fields
            
            start_time = self.__start_time
            start_time_obj=datetime.now()
            match=re.match('^([-+])?([0-9]+)$',start_time)
            if match is not None:
              delta=timedelta(minutes=int(match.group(2)))
              if match.group(1) == '-':
                start_time_obj-=delta
              else:
                start_time_obj+=delta

            start_time_obj = start_time_obj.replace(microsecond=0,second=0,tzinfo=None)
            querystring += '&startTime=' + start_time_obj.isoformat() + 'Z'
            if self.__observations is not None:
                timestep_suffix = self.__timesteps[-1]
                timestep_int = int(self.__timesteps[:-1])
                if timestep_suffix == 'm':
                    end_time = start_time_obj + timedelta(minutes=timestep_int*self.__observations)
                elif timestep_suffix == 'h':
                    end_time = start_time_obj + timedelta(hours=timestep_int*self.__observations)
                elif timestep_suffix == 'd':
                    end_time = start_time_obj + timedelta(days=timestep_int*self.__observations)
                
                querystring += '&endTime=' + end_time.isoformat() + 'Z'
              
            url = _ENDPOINT + '/timelines'
            _LOGGER.debug("ClimacellTimelineDataProvider:_user_update url: %s\%s.", url, querystring)
            self.data = self.__retrieve_data(url, self.__headers, querystring)

        return True

    def __retrieve_data(self, url, headers, querystring):
        result = self.data

        try:
            _LOGGER.debug("_retrieve_data url: %s - headers: %s - querystring: %s",
                          url, self.__headers, querystring)

            response = requests.request("GET", url,
                                        headers=headers, params=querystring,
                                        timeout=(10.05, 27), verify=True
                                        )

            if response.status_code == 200:
                result = json.loads(response.text)
                result = result['data']['timelines'][0]
            else:
                _LOGGER.error("ClimacellTimelineDataProvider._retrieve_data error status_code %s", response.status_code)

            _LOGGER.debug("_retrieve_data response.text: %s", response.text)

        except socket.error as err:
            _LOGGER.error("Unable to connect to Climatecell '%s' while try to retrieve data from %s.", err, url)
        
        return result
