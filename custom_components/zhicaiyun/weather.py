import logging
import random
import time
import voluptuous as vol
from datetime import timedelta, datetime

from homeassistant.components.weather import (
    ATTR_FORECAST_CONDITION, ATTR_FORECAST_PRECIPITATION, ATTR_FORECAST_TEMP,
    ATTR_FORECAST_TEMP_LOW, ATTR_FORECAST_TIME, ATTR_FORECAST_WIND_SPEED,
    ATTR_FORECAST_WIND_BEARING,
    PLATFORM_SCHEMA, WeatherEntity)
from homeassistant.const import (
    CONF_NAME, CONF_LONGITUDE, CONF_LATITUDE, TEMP_CELSIUS,
    CONF_SCAN_INTERVAL, STATE_UNKNOWN)
from homeassistant.helpers.event import async_track_time_interval
import homeassistant.helpers.config_validation as cv
#from homeassistant.util import Throttle

_LOGGER = logging.getLogger(__name__)

SCAN_INTERVAL = timedelta(minutes=1)

USER_AGENT = 'ColorfulCloudsPro/3.2.2 (iPhone; iOS 11.3; Scale/3.00)'
DEVIEC_ID = '5F544F93-44F1-43C9-94B2-%012X' % random.randint(0, 0xffffffffffff)

WEATHER_ICONS = {
    'CLEAR_NIGHT': 'clear-night',  # 晴（夜间）
    'CLOUDY': 'cloudy',  # 阴
    'FOG': 'fog',  # 雾
    'HAIL': 'hail',  # 冰雹
    # '': 'lightning', #雷电
    # '': 'lightning-rainy', #雷阵雨
    'PARTLY_CLOUDY_DAY': 'partlycloudy',  # 白天多云
    'PARTLY_CLOUDY_NIGHT': 'partlycloudy',  # 夜间多云
    # '': 'pouring', #暴雨
    'RAIN': 'rainy',  # 雨
    'SNOW': 'snowy',  # 雪
    'SLEET': 'snowy-rainy',  # 雨夹雪
    'CLEAR_DAY': 'sunny',  # 晴（白天）
    'WIND': 'windy',  # 大风
    'HAZE': 'windy-variant',  # 雾霾->有风
    # '': 'exceptional',
}

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend({
    vol.Optional(CONF_NAME, default='CaiYun'): cv.string,
    vol.Optional(CONF_LONGITUDE): cv.longitude,
    vol.Optional(CONF_LATITUDE): cv.latitude,
})


async def async_setup_platform(hass, conf, async_add_entities, discovery_info=None):
    """Set up the Caiyun sensor."""
    name = conf.get(CONF_NAME)
    longitude = str(conf.get(CONF_LONGITUDE, hass.config.longitude))
    latitude = str(conf.get(CONF_LATITUDE, hass.config.latitude))
    async_add_entities([ZhiCaiYunWeather(name, hass, longitude, latitude)], True)


class ZhiCaiYunWeather(WeatherEntity):

    def __init__(self, name, hass, longitude, latitude):
        self._name = name
        self._hass = hass
        self._longitude = longitude
        self._latitude = latitude
        self._data = {}

    @property
    def unique_id(self):
        return self.__class__.__name__.lower()

    @property
    def name(self):
        """Return the name of the sensor."""
        return self._name

    @property
    def condition(self):
        """Return the current condition."""
        return self._data.get('condition')

    @property
    def native_temperature(self):
        """Return the platform temperature."""
        return self._data.get('temperature')

    @property
    def native_temperature_unit(self):
        """Return the unit of measurement."""
        return TEMP_CELSIUS

    @property
    def native_pressure(self):
        """Return the pressure."""
        return self._data.get('pressure')

    @property
    def humidity(self):
        """Return the humidity."""
        return self._data.get('humidity')

    @property
    def native_wind_speed(self):
        """Return the wind speed."""
        return self._data.get('wind_speed')

    @property
    def wind_bearing(self):
        """Return the wind bearing."""
        return self._data.get('wind_bearing')

    @property
    def ozone(self):
        """Return the ozone level."""
        return self._data.get('ozone')

    @property
    def attribution(self):
        """Return the attribution."""
        return self._data.get('attribution')

    @property
    def native_visibility(self):
        """Return the visibility."""
        return self._data.get('visibility')

    @property
    def forecast(self):
        return self._data.get('forecast')

    @property
    def available(self):
        return bool(self._data)

    @property
    def state_attributes(self):
        """Return the state attributes."""
        attributes = super().state_attributes
        attributes['pm25'] = self._data.get('pm25')
        return attributes

    # @Throttle(timedelta(minutes=20))
    async def async_update(self):
        """Update Condition and Forecast."""
        data = {}
        try:
            headers = {'User-Agent': USER_AGENT,
                       'Accept': 'application/json',
                       'Accept-Language': 'zh-Hans-CN;q=1'}
            url = "http://api.caiyunapp.com/v2/UR8ASaplvIwavDfR/%s,%s/" \
                "weather?lang=zh_CN&tzshift=28800&timestamp=%d" \
                "&hourlysteps=384&dailysteps=16&alert=true&device_id=%s" % \
                (self._longitude, self._latitude, int(time.time()), DEVIEC_ID)
            #_LOGGER.debug(url)
            session = self._hass.helpers.aiohttp_client.async_get_clientsession()
            async with session.get(url, headers=headers) as r:
                resp = await r.json()
            #_LOGGER.info('gotWeatherData: %s', resp)
            result = resp['result']
            realtime = result['realtime']
            if realtime['status'] != 'ok':
                raise Exception(resp)

            # https://open.caiyunapp.com/%E5%AE%9E%E5%86%B5%E5%A4%A9%E6%B0%94%E6%8E%A5%E5%8F%A3/v2.2
            skycon = realtime['skycon']
            data['condition'] = WEATHER_ICONS[skycon] if skycon in WEATHER_ICONS else 'exceptional'

            data['temperature'] = round(realtime['temperature'])
            data['humidity'] = int(realtime['humidity'] * 100)
            data['pressure'] = int(realtime['pres'])
            wind = realtime.get('wind')
            if wind:
                data['wind_speed'] = wind.get('speed')
                data['wind_bearing'] = wind.get('direction')
            data['ozone'] = realtime.get('o3')
            data['visibility'] = realtime.get('visibility')
            data['attribution'] = result['forecast_keypoint']
            data['pm25'] = realtime.get('pm25')

            forecasts = {}
            daily = result['daily']
            for key in ['temperature', 'skycon', 'wind', 'precipitation']:
                for v in daily[key]:
                    date = v['date']
                    forecast = forecasts.get(date)
                    if forecast is None:
                        forecast = {
                            ATTR_FORECAST_TIME: datetime.strptime(date, '%Y-%m-%d')}
                        forecasts[date] = forecast
                    if key == 'temperature':
                        forecast[ATTR_FORECAST_TEMP] = v['avg']
                        forecast[ATTR_FORECAST_TEMP_LOW] = v['min']
                    elif key == 'skycon':
                        skycon = v['value']
                        forecast[ATTR_FORECAST_CONDITION] = WEATHER_ICONS[skycon] if skycon in WEATHER_ICONS else 'exceptional'
                    elif key == 'wind':
                        forecast[ATTR_FORECAST_WIND_BEARING] = v['avg']['direction']
                        forecast[ATTR_FORECAST_WIND_SPEED] = v['avg']['speed']
                    elif key == 'precipitation':
                        forecast[ATTR_FORECAST_PRECIPITATION] = v['avg']
            data['forecast'] = sorted(
                forecasts.values(), key=lambda k: k[ATTR_FORECAST_TIME])

        except:
            import traceback
            _LOGGER.error('exception: %s', traceback.format_exc())

        self._data = data
