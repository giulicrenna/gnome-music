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

import weakref

import gi
gi.require_version("Grl", "0.3")
from gi.repository import Grl, GLib, GObject, Gtk

from gnomemusic.grilowrappers.grlsearchwrapper import GrlSearchWrapper
from gnomemusic.grilowrappers.grltrackerwrapper import GrlTrackerWrapper
from gnomemusic.trackerwrapper import TrackerState, TrackerWrapper


class CoreGrilo(GObject.GObject):

    _blocklist = [
        'grl-bookmarks',
        'grl-filesystem',
        'grl-itunes-podcast',
        'grl-metadata-store',
        'grl-podcasts'
    ]

    _grl_plugin_ranks = ("grl-musicbrainz-coverart:3,"
                         "grl-lastfm-cover:2,"
                         "grl-theaudiodb-cover:1")

    _theaudiodb_api_key = "195003"

    cover_sources = GObject.Property(type=bool, default=False)
    tracker_available = GObject.Property(type=int)

    def __init__(self, application):
        """Initiate the CoreGrilo object

        :param Application application: The Application instance to use
        """
        super().__init__()

        self._application = application
        self._coremodel = self._application.props.coremodel
        self._coreselection = application.props.coreselection
        self._log = application.props.log
        self._search_wrappers = {}
        self._thumbnail_sources = []
        self._thumbnail_sources_timeout = None
        self._wrappers = {}

        self._tracker_wrapper = TrackerWrapper(application)
        self._tracker_wrapper.bind_property(
            "tracker-available", self, "tracker-available",
            GObject.BindingFlags.SYNC_CREATE)

        GLib.setenv("GRL_PLUGIN_RANKS", self._grl_plugin_ranks, True)

        Grl.init(None)

        self._registry = Grl.Registry.get_default()
        config = Grl.Config.new("grl-lua-factory", "grl-theaudiodb-cover")
        config.set_api_key(self._theaudiodb_api_key)
        self._registry.add_config(config)

        self._registry.connect('source-added', self._on_source_added)
        self._registry.connect('source-removed', self._on_source_removed)

        self._registry.load_all_plugins(False)

        tracker_available_state = self._tracker_wrapper.props.tracker_available
        if tracker_available_state != TrackerState.AVAILABLE:
            self._tracker_wrapper.connect(
                "notify::tracker-available",
                self._on_tracker_available_changed)
        else:
            self._on_tracker_available_changed(None, None)

        for plugin in self._registry.get_plugins(False):
            plugin_id = plugin.get_id()
            # Activate the Tracker plugin only when TrackerWrapper
            # is available by listening to the tracker-available
            # property, so skip it here.
            if plugin_id != "grl-tracker3":
                try:
                    self._registry.activate_plugin_by_id(plugin_id)
                except GLib.GError:
                    self._log.debug(
                        "Failed to activate {} plugin.".format(plugin_id))

        weakref.finalize(self, Grl.deinit)

    def _on_tracker_available_changed(self, klass, value):
        # FIXME:No removal support yet.
        new_state = self._tracker_wrapper.props.tracker_available
        if new_state == TrackerState.AVAILABLE:
            config = Grl.Config.new("grl-tracker3", "grl-tracker3-source")
            config.set_string(
                "miner-service", self._tracker_wrapper.props.miner_fs_busname)
            config.set_string(
                "store-path", self._tracker_wrapper.cache_directory())
            self._registry.add_config(config)

            self._registry.activate_plugin_by_id("grl-tracker3")

    def _on_source_added(self, registry, source):

        def _trigger_art_update():
            self._thumbnail_sources_timeout = None
            if len(self._thumbnail_sources) > 0:
                self.props.cover_sources = True

            return GLib.SOURCE_REMOVE

        if ("net:plaintext" in source.get_tags()
                or source.props.source_id in self._blocklist):
            try:
                registry.unregister_source(source)
            except GLib.GError:
                self._log.warning(
                    "Failed to unregister {}".format(source.props.source_id))
            return

        if Grl.METADATA_KEY_THUMBNAIL in source.supported_keys():
            self._thumbnail_sources.append(source)
            if not self._thumbnail_sources_timeout:
                # Aggregate sources being added, for example when the
                # network comes online.
                self._thumbnail_sources_timeout = GLib.timeout_add_seconds(
                    5, _trigger_art_update)

        if (source.props.source_id == "grl-tracker3-source"
                and self._tracker_wrapper.location_filter() is not None):
            new_wrapper = GrlTrackerWrapper(
                source, self._application, self._tracker_wrapper)
            self._wrappers[source.props.source_id] = new_wrapper
            self._log.debug("Adding wrapper {}".format(new_wrapper))
            music_dir = GLib.get_user_special_dir(
                GLib.UserDirectory.DIRECTORY_MUSIC)
            self._log.debug("XDG Music dir is: {}".format(music_dir))
        elif (source.props.source_id not in self._search_wrappers.keys()
                and source.props.source_id not in self._wrappers.keys()
                and source.props.source_id != "grl-tracker3-source"
                and source.get_supported_media() & Grl.MediaType.AUDIO
                and source.supported_operations() & Grl.SupportedOps.SEARCH
                and "net:internet" not in source.props.source_tags):
            self._search_wrappers[source.props.source_id] = GrlSearchWrapper(
                source, self._application)
            self._log.debug("Adding search source {}".format(source))

    def _on_source_removed(self, registry, source):
        # FIXME: Handle removing sources.
        self._log.debug("Removed source {}".format(source.props.source_id))

        # FIXME: Only removes search sources atm.
        self._search_wrappers.pop(source.props.source_id, None)

    def get_artist_albums(self, media, filter_model):
        """Get all album by an artist

        :param Grl.Media media: A Grilo Media item that represents Artist
        :param Gtk.FilterListModel filter_model: The model to fill
        """
        source = media.get_source()
        self._wrappers[source].get_artist_albums(media, filter_model)

    def get_album_discs(self, media, disc_model):
        """Get all discs from an album

        :param Grl.Media media: A Grilo Media item that represents Album
        :param Gtk.SortListModel disc_model: The model to fill
        """
        source = media.get_source()
        self._wrappers[source].get_album_discs(media, disc_model)

    def get_album_disc(
            self, media: Grl.Media, discnr: int,
            model: Gtk.FilterListModel) -> None:
        """Get all songs from an album disc

        :param Grl.Media media: An album
        :param int discnr: The disc number
        :param Gtk.FilterListModel model: The model to fill
        """
        source = media.get_source()
        self._wrappers[source].get_album_disc(media, discnr, model)

    def writeback(self, media, key):
        """Store the values associated with the key.

        :param Grl.Media media: A Grilo media item
        :param int key: a Grilo metadata key
        """
        def _store_metadata_cb(source, media, failed_keys, data, error):
            if error is not None:
                self._log.warning(
                    "Error {}: {}".format(error.domain, error.message))
            if failed_keys:
                self._log.warning("Unable to update {}".format(failed_keys))

        for wrapper in self._wrappers.values():
            if media.get_source() == wrapper.source.props.source_id:
                wrapper.props.source.store_metadata(
                    media, [key], Grl.WriteFlags.NORMAL, _store_metadata_cb,
                    None)
                break

    def writeback_tracker(self, media, tag):
        """Use Tracker queries to update tags.

        The tags are associated with a Tracker resource
        (song, album, artist or external resource), so they can cannot
        be updated with grilo writeback support.

        :param Grl.Media media: A Grilo media item
        :param str tag: tag to update
        """
        self._tracker_wrapper.update_tag(media, tag)

    def search(self, text):
        for wrapper in self._wrappers.values():
            wrapper.search(text)
        for wrapper in self._search_wrappers.values():
            wrapper.search(text)

    def get_song_art(self, coresong, storeart=None):
        """Retrieve song art for the given CoreSong

        :param CoreSong coresong: CoreSong to retrieve art for
        :param StoreArt storeart: StoreArt instance or None
        """
        if "grl-tracker3-source" in self._wrappers:
            self._wrappers["grl-tracker3-source"].get_song_art(
                coresong, storeart)

    def get_album_art(self, corealbum, storeart=None):
        """Retrieve album art for the given CoreAlbum

        :param CoreAlbum corealbum: CoreAlbum to retrieve art for
        :param StoreArt storeart: StoreArt instance or None
        """
        if "grl-tracker3-source" in self._wrappers:
            self._wrappers["grl-tracker3-source"].get_album_art(
                corealbum, storeart)

    def get_artist_art(self, coreartist, storeart=None):
        """Retrieve artist art for the given CoreArtist

        :param CoreArtist coreartist: CoreArtist to retrieve art for
        :param StoreArt storeart: StoreArt instance or None
        """
        if "grl-tracker3-source" in self._wrappers:
            self._wrappers["grl-tracker3-source"].get_artist_art(
                coreartist, storeart)

    def stage_playlist_deletion(self, playlist):
        """Prepares playlist deletion.

        :param Playlist playlist: playlist
        """
        if "grl-tracker3-source" in self._wrappers:
            self._wrappers["grl-tracker3-source"].stage_playlist_deletion(
                playlist)

    def finish_playlist_deletion(self, playlist, deleted):
        """Finishes playlist deletion.

        :param Playlist playlist: playlist
        :param bool deleted: indicates if the playlist has been deleted
        """
        if "grl-tracker3-source" in self._wrappers:
            self._wrappers["grl-tracker3-source"].finish_playlist_deletion(
                playlist, deleted)

    def create_playlist(self, playlist_title, callback):
        """Creates a new user playlist.

        :param str playlist_title: playlist title
        :param callback: function to perform once, the playlist is created
        """
        if "grl-tracker3-source" in self._wrappers:
            self._wrappers["grl-tracker3-source"].create_playlist(
                playlist_title, callback)
