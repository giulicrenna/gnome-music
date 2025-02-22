# Copyright 2019 The GNOME Music developers
#
# GNOME Music is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# GNOME Music is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License along
# with GNOME Music; if not, write to the Free Software Foundation, Inc.,
# 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301 USA.
#
# The GNOME Music authors hereby grant permission for non-GPL compatible
# GStreamer plugins to be used and distributed together with GStreamer
# and GNOME Music.  This permission is above and beyond the permissions
# granted by the GPL license by which GNOME Music is covered.  If you
# modify this code, you may extend this exception to your version of the
# code, but you are not obligated to do so.  If you do not wish to do so,
# delete this exception statement from your version.

from __future__ import annotations

import gi
gi.require_versions({"Grl": "0.3"})
from gi.repository import Gio, Grl, Gtk, GObject

import gnomemusic.utils as utils

from gnomemusic.albumart import AlbumArt


class CoreAlbum(GObject.GObject):
    """Exposes a Grl.Media with relevant data as properties
    """

    __gtype_name__ = "CoreAlbum"

    artist = GObject.Property(type=str)
    composer = GObject.Property(type=str, default=None)
    duration = GObject.Property(type=int, default=0)
    media = GObject.Property(type=Grl.Media)
    title = GObject.Property(type=str)
    url = GObject.Property(type=str)
    year = GObject.Property(type=str, default=None)

    def __init__(self, application, media):
        """Initiate the CoreAlbum object

        :param Application application: The application object
        :param Grl.Media media: A media object
        """
        super().__init__()

        self._application = application
        self._coregrilo = application.props.coregrilo
        self._model = None
        self._selected = False
        self._thumbnail = None

        self.update(media)

    def update(self, media):
        """Update the CoreAlbum object with new info

        :param Grl.Media media: A media object
        """
        self.props.media = media
        self.props.artist = utils.get_artist_name(media)
        self.props.composer = media.get_composer()
        self.props.title = utils.get_media_title(media)
        self.props.url = media.get_url()
        self.props.year = utils.get_media_year(media)

    def _get_album_model(self):
        disc_model = Gio.ListStore()
        disc_model_sort = Gtk.SortListModel.new(disc_model)

        def _disc_order_sort(disc_a, disc_b, data=None):
            order = disc_a.props.disc_nr - disc_b.props.disc_nr
            if order < 0:
                return Gtk.Ordering.SMALLER
            elif order > 0:
                return Gtk.Ordering.LARGER
            else:
                return Gtk.Ordering.EQUAL

        disc_sorter = Gtk.CustomSorter()
        disc_sorter.set_sort_func(_disc_order_sort)
        disc_model_sort.set_sorter(disc_sorter)

        self._coregrilo.get_album_discs(self.props.media, disc_model)

        return disc_model_sort

    @GObject.Property(
        type=Gtk.SortListModel, default=None,
        flags=GObject.ParamFlags.READABLE)
    def model(self):
        if self._model is None:
            self._model = self._get_album_model()
            self._model.connect("items-changed", self._on_list_items_changed)
            self._model.items_changed(0, 0, self._model.get_n_items())

        return self._model

    def _on_list_items_changed(self, model, position, removed, added):
        with self.freeze_notify():
            for coredisc in model:
                coredisc.props.selected = self.props.selected

            if added > 0:
                for i in range(added):
                    coredisc = model[position + i]
                    coredisc.connect(
                        "notify::duration", self._on_duration_changed)

    def _on_duration_changed(self, coredisc, duration):
        duration = 0

        for coredisc in self.props.model:
            duration += coredisc.props.duration

        self.props.duration = duration

    @GObject.Property(type=bool, default=False)
    def selected(self):
        return self._selected

    @selected.setter  # type: ignore
    def selected(self, value):
        if value == self._selected:
            return

        self._selected = value

        # The model is loaded on-demand, so the first time the model is
        # returned it can still be empty. This is problem for returning
        # a selection. Trigger loading of the model here if a selection
        # is requested, it will trigger the filled model update as
        # well.
        self.props.model.items_changed(0, 0, 0)

    @GObject.Property(type=str, default=None)
    def thumbnail(self):
        """Album art thumbnail retrieval

        :return: The album art uri or "generic"
        :rtype: string
        """
        if self._thumbnail is None:
            self._thumbnail = "generic"
            AlbumArt(self._application, self)

        return self._thumbnail

    @thumbnail.setter  # type: ignore
    def thumbnail(self, value):
        """Album art thumbnail setter

        :param string value: uri or "generic"
        """
        self._thumbnail = value

        if self._thumbnail != "generic":
            self.props.media.set_thumbnail(self._thumbnail)

    @GObject.Property(type=object, flags=GObject.ParamFlags.READABLE)
    def corealbum(self) -> CoreAlbum:
        return self
