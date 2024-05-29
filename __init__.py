import tempfile
from datetime import datetime
from os.path import join, dirname
from time import sleep

import matplotlib.pyplot as plt
import requests
from lingua_franca.format import nice_duration
from matplotlib.offsetbox import OffsetImage, AnnotationBbox
from mpl_toolkits.basemap import Basemap
from ovos_workshop.decorators import intent_handler
from ovos_workshop.decorators import resting_screen_handler
from ovos_workshop.intents import IntentBuilder
from ovos_workshop.skills import OVOSSkill


class ISSLocationSkill(OVOSSkill):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
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
        if "iss_icon" not in self.settings:
            self.settings["iss_icon"] = f"{self.root_dir}/ui/iss3.png"
        if "iss_bg" not in self.settings:
            self.settings["iss_bg"] = f"{self.root_dir}/ui/iss.png"
        if "dpi" not in self.settings:
            self.settings["dpi"] = 500

    def update_picture(self):
        try:
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

            image = self.generate_map(lat, lon)

            self.gui['imgLink'] = image
            self.gui['caption'] = f"{toponym} Lat: {lat}  Lon: {lon}"
            self.gui['lat'] = lat
            self.gui['lot'] = lon
            self.gui["astronauts"] = astronauts["people"]
            self.set_context("iss")
            return image
        except Exception as e:
            self.log.exception(e)

    @resting_screen_handler("ISS")
    def idle(self, message):
        self.update_picture()  # values available in self.gui
        self.gui.clear()
        self.gui.show_image(self.gui['imgLink'], fill='PreserveAspectFit')

    def generate_map(self, lat, lon):
        lat = float(lat)
        lon = float(lon)
        icon = join(dirname(__file__), self.settings["iss_icon"])
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

        iss = plt.imread(icon)
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

    @intent_handler("about.intent")
    def handle_about_iss_intent(self, message):
        utterance = self.dialog_renderer.render("about", {})
        self.gui.show_image(self.settings["iss_bg"],
                            override_idle=True,
                            fill='PreserveAspectFit',
                            caption=utterance)
        self.speak(utterance, wait=True)
        sleep(1)
        self.gui.clear()

    @intent_handler('where_iss.intent')
    def handle_iss(self, message):
        self.update_picture()  # values available in self.gui
        self.gui.show_image(self.gui['imgLink'],
                            caption=self.gui['caption'],
                            fill='PreserveAspectFit')
        if self.gui['toponym'] == "unknown":
            self.speak_dialog("location.unknown", {
                "latitude": self.gui['lat'],
                "longitude": self.gui['lon']
            }, wait=True)
        else:
            self.speak_dialog("location.current", {
                "latitude": self.gui['lat'],
                "longitude": self.gui['lon'],
                "toponym": self.gui['toponym']
            }, wait=True)
        sleep(1)
        self.gui.clear()

    @intent_handler('when_iss.intent')
    def handle_when(self, message):
        lat = self.location["coordinate"]["latitude"]
        lon = self.location["coordinate"]["longitude"]
        params = {"lat": lat, "lon": lon}
        passing = requests.get("http://api.open-notify.org/iss-pass.json",
                               params=params).json()

        next_passage = passing["response"][0]
        ts = next_passage["risetime"]
        dt = datetime.fromtimestamp(ts)
        delta = datetime.now() - dt
        duration = nice_duration(delta, lang=self.lang)
        caption = self.location_pretty + " " + dt.strftime(
            "%m/%d/%Y, %H:%M:%S")
        image = self.generate_map(lat, lon)

        self.gui.show_image(image, caption=caption, fill='PreserveAspectFit')

        self.speak_dialog("location.when", {
            "duration": duration,
            "toponym": self.location_pretty
        }, wait=True)
        sleep(1)
        self.gui.clear()

    @intent_handler(
        IntentBuilder("WhoISSIntent").require("who").require(
            "onboard").require("iss"))
    def handle_who(self, message):
        self.update_picture()  # values available in self.gui
        people = [
            p["name"] for p in self.gui["astronauts"]
            if p["craft"] == "ISS"
        ]
        people = ", ".join(people)
        self.gui.show_image(self.settings["iss_bg"],
                            override_idle=True,
                            fill='PreserveAspectFit',
                            caption=people)
        self.speak_dialog("who", {"people": people}, wait=True)
        sleep(1)
        self.gui.clear()

    @intent_handler(
        IntentBuilder("NumberISSIntent").require("how_many").require(
            "onboard").require("iss"))
    def handle_number(self, message):
        self.update_picture()  # values available in self.gui
        people = [
            p["name"] for p in self.gui["astronauts"]
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
        self.gui.clear()


if __name__ == "__main__":
    from ovos_utils.fakebus import FakeBus

    s = ISSLocationSkill(skill_id="fake.test", bus=FakeBus())
    s.update_picture()
