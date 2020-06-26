from mycroft import MycroftSkill, intent_file_handler, intent_handler
from mycroft.skills.core import resting_screen_handler
import matplotlib.pyplot as plt
from mpl_toolkits.basemap import Basemap
import tempfile
from os.path import join, dirname
from matplotlib.offsetbox import OffsetImage, AnnotationBbox
from time import sleep
from requests_cache import CachedSession
from datetime import timedelta, datetime
from mtranslate import translate


class ISSLocationSkill(MycroftSkill):
    def __init__(self):
        super(ISSLocationSkill, self).__init__(name="I S S Location Skill")
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
            self.settings["iss_icon"] = "iss3.png"
        if "dpi" not in self.settings:
            self.settings["dpi"] = 500
        _expire_after = timedelta(minutes=10)
        self._session = CachedSession(backend='memory',
                                      expire_after=_expire_after)

    def update_picture(self):
        try:
            data = self._session.get(
                "http://api.open-notify.org/iss-now.json").json()
            lat = data['iss_position']['latitude']
            lon = data['iss_position']['longitude']
            if not self.settings.get("lat") or \
                    not self.settings.get("lon") or \
                    lat != self.settings['lat'] or \
                    lon != self.settings['lon']:
                params = {
                    "username": self.settings["geonames_user"],
                    "lat": lat,
                    "lng": lon
                }
                ocean_names = "http://api.geonames.org/oceanJSON"
                land_names = "http://api.geonames.org/countryCodeJSON"

                # reverse geo
                data = self._session.get(ocean_names, params=params).json()
                try:
                    toponym = "the " + data['ocean']['name']
                except:

                    try:
                        params = {
                            "username": self.settings["geonames_user"],
                            "lat": lat,
                            "lng": lon,
                            "formatted": True,
                            "style": "full"
                        }
                        data = self._session.get(land_names,
                                                 params=params).json()
                        toponym = data['countryName']
                    except:
                        toponym = "unknown"
                if not self.lang.lower().startswith("en") and \
                        toponym != "unknown":
                    toponym = translate(toponym, self.lang)
                self.settings['toponym'] = toponym
                image = self.generate_map(lat, lon)

                self.settings['lat'] = lat
                self.settings['lon'] = lon
                self.settings['imgLink'] = image

        except Exception as e:
            self.log.exception(e)
        self.gui['imgLink'] = self.settings['imgLink']
        self.gui['caption'] = str(datetime.now()) + " " + \
                              self.settings['toponym']
        self.gui['lat'] = self.settings['lat']
        self.gui['lot'] = self.settings['lon']

    @resting_screen_handler("ISS")
    def idle(self, message):
        self.update_picture()
        self.gui.clear()
        self.gui.show_page('idle.qml')

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
                    resolution=None, lat_0=lat_0, lon_0=lon_0)
        m.bluemarble()
        x, y = m(lon, lat)

        iss = plt.imread(icon)
        im = OffsetImage(iss, zoom=self.settings["iss_size"])
        ab = AnnotationBbox(im, (x, y), xycoords='data', frameon=False)

        # Get the axes object from the basemap and add the AnnotationBbox artist
        m._check_ax().add_artist(ab)

        plt.savefig(output, dpi=self.settings["dpi"], bbox_inches='tight')
        return output

    @intent_file_handler("about.intent")
    def handle_about_iss_intent(self, message):
        epic = join(dirname(__file__), "ui", "images", "iss.png")
        utterance = self.dialog_renderer.render("about", {})
        self.gui.show_image(epic, override_idle=True,
                            fill='PreserveAspectFit', caption=utterance)
        self.speak(utterance, wait=True)
        sleep(1)
        self.gui.clear()

    @intent_file_handler('where_iss.intent')
    def handle_iss(self, message):
        self.update_picture()
        self.gui.show_image(self.settings['imgLink'],
                            caption=self.gui['caption'],
                            fill='PreserveAspectFit')
        if self.settings['toponym'] == "unknown":
            self.speak_dialog("location.unknown",
                              {"latitude": self.settings['lat'],
                               "longitude": self.settings['lon']},
                              wait=True)
        else:
            self.speak_dialog("location.current",
                              {"latitude": self.settings['lat'],
                               "longitude":  self.settings['lon'],
                               "toponym":  self.settings['toponym']},
                              wait=True)
        sleep(1)
        self.gui.clear()


def create_skill():
    return ISSLocationSkill()
