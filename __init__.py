import tempfile
from datetime import datetime, timedelta
from os.path import join
from time import sleep

import pytz
import requests
from ovos_date_parser import nice_duration
from ovos_utils.time import to_local, now_local
from ovos_workshop.decorators import intent_handler
from ovos_workshop.intents import IntentBuilder
from ovos_workshop.skills import OVOSSkill
from skyfield.api import Topos, load

try:
    import matplotlib.pyplot as plt
    from matplotlib.offsetbox import OffsetImage, AnnotationBbox
    from mpl_toolkits.basemap import Basemap
    GUI = True
except ImportError:
    GUI = False


class ISSLocationSkill(OVOSSkill):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if "enable_gui" not in self.settings:
            self.settings["enable_gui"] = False
        if "geonames_user" not in self.settings:
            self.settings["geonames_user"] = "jarbas"
        if "map_style" not in self.settings:
            self.settings["map_style"] = "ortho"
        if "center_iss" not in self.settings:
            self.settings["center_iss"] = True
        if "center_location" not in self.settings:
            self.settings["center_location"] = False
        if "iss_size" not in self.settings:
            self.settings["iss_size"] = 0.5
        if "dpi" not in self.settings:
            self.settings["dpi"] = 500

    def initialize(self):
        if self.use_gui:
            # equivalent to using the resting_screen_handler decorator
            # but we only do it if GUI is enabled
            self.idle.resting_handler = "ISS Location"
            self.register_resting_screen()

    @property
    def use_gui(self) -> bool:
        return GUI and self.settings["enable_gui"]

    def get_iss_data(self):
        data = requests.get("http://api.open-notify.org/iss-now.json").json()
        astronauts = requests.get("http://api.open-notify.org/astros.json").json()

        lat = data['iss_position']['latitude']
        lon = data['iss_position']['longitude']

        params = {
            "username": self.settings["geonames_user"],
            "lat": lat,
            "lng": lon
        }
        ocean_names = "http://api.geonames.org/oceanJSON"
        land_names = "http://api.geonames.org/countryCodeJSON"

        # reverse geo
        data = requests.get(ocean_names, params=params).json()
        try:
            toponym = "The " + data['ocean']['name']
        except:

            try:
                params = {
                    "username": self.settings["geonames_user"],
                    "lat": lat,
                    "lng": lon,
                    "formatted": True,
                    "style": "full"
                }
                data = requests.get(land_names,
                                    params=params).json()
                toponym = data['countryName']
            except:
                toponym = "unknown"
        if not self.lang.lower().startswith("en") and toponym != "unknown":
            toponym = self.translator.translate(toponym, self.lang)
        return toponym, lat, lon, astronauts

    def update_picture(self, toponym, lat, lon, astronauts):
        try:
            image = self.generate_map(lat, lon)
            self.gui['imgLink'] = image
            self.gui['caption'] = f"{toponym} Lat: {lat}  Lon: {lon}"
            self.gui['lat'] = lat
            self.gui['lon'] = lon
            self.gui['toponym'] = toponym
            self.gui["astronauts"] = astronauts["people"]
            self.set_context("iss")
        except Exception as e:
            self.log.exception(e)

    def idle(self, message):
        toponym, lat, lon, astronauts = self.get_iss_data()
        self.update_picture(toponym, lat, lon, astronauts)  # values available in self.gui
        self.gui.show_image(self.gui['imgLink'], fill='PreserveAspectFit')

    def generate_map(self, lat, lon):
        lat = float(lat)
        lon = float(lon)
        output = join(tempfile.gettempdir(), "iss.jpg")
        lat_0 = None
        lon_0 = None
        if self.settings["center_iss"]:
            lat_0 = lat
            lon_0 = lon
        elif self.settings["center_location"]:
            lat_0 = self.location["coordinate"]["latitude"]
            lon_0 = self.location["coordinate"]["longitude"]
        if self.settings["map_style"] == "cyl":
            lat_0 = None
            lon_0 = None
        m = Basemap(projection=self.settings["map_style"],
                    resolution=None,
                    lat_0=lat_0,
                    lon_0=lon_0)
        m.bluemarble()
        x, y = m(lon, lat)

        iss = plt.imread(self.settings.get("iss_icon", f"{self.root_dir}/gui/all/iss3.png"))
        im = OffsetImage(iss, zoom=self.settings["iss_size"])
        ab = AnnotationBbox(im, (x, y), xycoords='data', frameon=False)

        # Get the axes object from the basemap and add the AnnotationBbox artist
        m._check_ax().add_artist(ab)

        plt.savefig(output,
                    dpi=self.settings["dpi"],
                    bbox_inches='tight',
                    facecolor="black")
        plt.close()
        return output

    @intent_handler('where_iss.intent')
    def handle_iss(self, message):
        toponym, lat, lon, astronauts = self.get_iss_data()
        if self.use_gui:
            self.update_picture(toponym, lat, lon, astronauts)
            self.gui.show_image(self.gui['imgLink'],
                                caption=self.gui['caption'],
                                fill='PreserveAspectFit')

        if toponym == "unknown":
            self.speak_dialog("location.unknown", {
                "latitude": lat,
                "longitude": lon
            }, wait=True)
        else:
            self.speak_dialog("location.current", {
                "latitude": lat,
                "longitude":lon,
                "toponym": toponym
            }, wait=True)
        sleep(1)
        self.gui.release()

    @intent_handler('when_iss.intent')
    def handle_when(self, message):
        lat = self.location["coordinate"]["latitude"]
        lon = self.location["coordinate"]["longitude"]

        pred = SatellitePredictions(lat, lon, altitude=0, days=1).predict()
        dt = pred["rise"]["time"]  # in user timezone
        delta = pred["length"]
        dur = dt - now_local()

        duration = nice_duration(dur, lang=self.lang)
        visible_dur = nice_duration(delta, lang=self.lang)
        if self.use_gui:
            caption = self.location_pretty + " " + dt.strftime("%m/%d/%Y, %H:%M:%S")
            image = self.generate_map(lat, lon)
            self.gui.show_image(image, caption=caption, fill='PreserveAspectFit')

        self.speak_dialog("location.when", {
            "duration": duration,
            "toponym": self.location_pretty
        }, wait=True)
        self.speak_dialog("visible_for", {
            "duration": visible_dur
        }, wait=True)
        self.gui.release()

    @intent_handler(IntentBuilder("WhoISSIntent").require("who").
                    require("onboard").require("iss"))
    def handle_who(self, message):
        toponym, lat, lon, astronauts = self.get_iss_data()
        people = [
            p["name"] for p in astronauts
            if p["craft"] == "ISS"
        ]
        people = ", ".join(people)
        if self.use_gui:
            self.update_picture(toponym, lat, lon, astronauts)
            self.gui.show_image(self.settings["iss_bg"],
                                override_idle=True,
                                fill='PreserveAspectFit',
                                caption=people)
        self.speak_dialog("who", {"people": people}, wait=True)
        sleep(1)
        self.gui.release()

    @intent_handler(IntentBuilder("NumberISSIntent").require("how_many")
                    .require("onboard").require("iss"))
    def handle_number(self, message):

        toponym, lat, lon, astronauts = self.get_iss_data()
        people = [
            p["name"] for p in astronauts
            if p["craft"] == "ISS"
        ]
        num = len(people)
        people = ", ".join(people)
        self.gui.show_image(self.settings["iss_bg"],
                            override_idle=True,
                            fill='PreserveAspectFit',
                            caption=people)
        self.speak_dialog("number", {"number": num}, wait=True)
        sleep(1)
        self.gui.release()


class SatellitePredictions:
    # taken from https://github.com/yuvadm/iss.guru/blob/master/iss/predictions.py
    ISS = "ISS (ZARYA)"
    STATIONS_URL = "http://celestrak.com/NORAD/elements/stations.txt"

    def __init__(self, lat, lon, altitude=0, tz="UTC", satellite=ISS, start=None, days=10):
        self.lat = lat
        self.lon = lon
        self.altitude = altitude
        self.tz = tz
        self.start = start
        self.days = days

        satellites = load.tle_file(self.STATIONS_URL)
        self.satellite = {sat.name: sat for sat in satellites}[satellite]
        self.location = Topos(latitude_degrees=self.lat, longitude_degrees=self.lon)

    @staticmethod
    def to_local_time(utc_iso: str):
        """ensure datetime object is in user timezone"""
        naive_datetime = datetime.strptime(utc_iso, '%Y-%m-%dT%H:%M:%SZ')
        utc_timezone = pytz.timezone('UTC')
        dt = utc_timezone.localize(naive_datetime)
        return to_local(dt)

    @staticmethod
    def chunks(l, n):
        for i in range(0, len(l), n):
            yield l[i: i + n]

    @staticmethod
    def deg_to_cardinal(deg):
        cardinals = [
            "N",
            "NNE",
            "NE",
            "ENE",
            "E",
            "ESE",
            "SE",
            "SSE",
            "S",
            "SSW",
            "SW",
            "WSW",
            "W",
            "WNW",
            "NW",
            "NNW",
        ]
        return cardinals[round((deg % 360) / 22.5) % 16]

    @staticmethod
    def seconds_to_minutes(secs):
        return f"{secs // 60}:{secs % 60:02}"

    def get_next_days(self):
        ts = load.timescale()
        t0 = ts.now() if not self.start else ts.ut1_jd(self.start)
        t1 = ts.ut1_jd(t0.ut1 + self.days)
        return t0, t1

    def get_position_details(self, t):
        difference = self.satellite - self.location
        topocentric = difference.at(t)
        alt, az, distance = topocentric.altaz()
        azimuth = int(az.degrees)
        return {
            "time": self.to_local_time(t.utc_iso()),
            "degrees": int(alt.degrees),
            "azimuth": azimuth,
            "direction": self.deg_to_cardinal(azimuth),
            "distance": int(distance.km),
        }

    def get_prediction_events(self):
        t0, t1 = self.get_next_days()

        ts, _events = self.satellite.find_events(
            self.location, t0, t1, altitude_degrees=self.altitude
        )

        # events are returned as 3-tuples of (rise, culminate, set)
        # where rise/set are relative to given altitude
        # docs mention the possibility of several culminations
        # https://rhodesmill.org/skyfield/earth-satellites.html#finding-when-a-satellite-rises-and-sets
        # but this doesn't seem to happen in our case
        res = list(self.chunks(ts, 3))

        if len(res[-1]) != 3:
            # truncate the last event in case it's a partial one
            res = res[:-1]

        return res

    def predict(self):
        preds = self.get_prediction_events()
        rise, culminate, zet = preds[0]
        length = int((zet - rise) * 86400)
        return {
            "length": timedelta(seconds=length),
            "length_mins": self.seconds_to_minutes(length),
            "rise": self.get_position_details(rise),
            "culminate": self.get_position_details(culminate),
            "set": self.get_position_details(zet),
        }


if __name__ == "__main__":
    from ovos_utils.fakebus import FakeBus
    from ovos_bus_client.message import Message
    from ovos_config.locale import setup_locale

    setup_locale()


    # print speak for debugging
    def spk(utt, *args, **kwargs):
        print(utt)


    s = ISSLocationSkill(skill_id="fake.test", bus=FakeBus())
    # s.update_picture()
    s.speak = spk

    s.handle_number(Message(""))
    # there are 7 persons on board of the international space station
    s.handle_who(Message(""))
    # Jasmin Moghbeli, Andreas Mogensen, Satoshi Furukawa, Konstantin Borisov, Oleg Kononenko, Nikolai Chub, Loral O'Hara are in orbit on board of the space station
    s.handle_iss(Message(""))
    # The international space station is now over Central African Republic at 8.6270 latitude 21.5912 longitude
    s.handle_when(Message(""))
    # The I S S will be over XXX in seven minutes twenty five seconds
    # It will be visible during seven minutes twenty five seconds
    s.handle_about_iss_intent(Message(""))
    # The International Space Station is a modular space station in low Earth orbit. The ISS programme is a multi-national collaborative project between five participating space agencies: NASA ( United States ) , Roscosmos ( Russia ) , JAXA ( Japan ) , ESA ( Europe ) , and CSA ( Canada ) .The ownership and use of the space station is established by intergovernmental treaties and agreements.
