# Copyright © 2018 The GNOME Music Developers
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

from gettext import gettext as _
from gi.repository import Gio, GLib, GObject, Gtk

from gnomemusic.coverpaintable import CoverPaintable
from gnomemusic.gstplayer import Playback
from gnomemusic.utils import ArtSize, DefaultIconType
from gnomemusic.player import Player, RepeatMode
from gnomemusic.widgets.smoothscale import SmoothScale  # noqa: F401
from gnomemusic.widgets.twolinetip import TwoLineTip
import gnomemusic.utils as utils


@Gtk.Template(resource_path='/org/gnome/Music/ui/PlayerToolbar.ui')
class PlayerToolbar(Gtk.ActionBar):
    """Main Player widget object

    Contains the ui of playing a song with Music.
    """

    __gtype_name__ = 'PlayerToolbar'

    _artist_label = Gtk.Template.Child()
    _cover_image = Gtk.Template.Child()
    _duration_label = Gtk.Template.Child()
    _next_button = Gtk.Template.Child()
    _play_button = Gtk.Template.Child()
    _play_pause_image = Gtk.Template.Child()
    _prev_button = Gtk.Template.Child()
    _progress_scale = Gtk.Template.Child()
    _progress_time_label = Gtk.Template.Child()
    _repeat_menu_button = Gtk.Template.Child()
    _repeat_image = Gtk.Template.Child()
    _song_info_box = Gtk.Template.Child()
    _title_label = Gtk.Template.Child()

    def __init__(self):
        super().__init__()

        self._player = None

        self._cover_image.set_size_request(
            ArtSize.SMALL.width, ArtSize.SMALL.height)
        self._cover_image.props.paintable = CoverPaintable(
            self, ArtSize.SMALL, DefaultIconType.ALBUM)

        self._tooltip = TwoLineTip()

        repeat_menu = Gio.Menu.new()
        for mode in RepeatMode:
            item = Gio.MenuItem.new()
            item.set_label(mode.label)
            item.set_action_and_target_value(
                "playertoolbar.repeat", GLib.Variant("s", str(mode.value)))
            repeat_menu.append_item(item)

        self._repeat_menu_button.props.menu_model = repeat_menu
        self._repeat_action: Gio.SimpleAction = Gio.SimpleAction.new_stateful(
            "repeat", GLib.VariantType.new("s"), GLib.Variant("s", ""))

        action_group = Gio.SimpleActionGroup()
        action_group.add_action(self._repeat_action)
        self.insert_action_group("playertoolbar", action_group)

    # FIXME: This is a workaround for not being able to pass the player
    # object via init when using Gtk.Builder.
    @GObject.Property(type=Player, default=None)
    def player(self):
        """The GstPlayer object used

        :return: player object
        :rtype: GstPlayer
        """
        return self._player

    @player.setter  # type: ignore
    def player(self, player):
        """Set the GstPlayer object used

        :param GstPlayer player: The GstPlayer to use
        """
        if (player is None
                or (self._player is not None
                    and self._player != player)):
            return

        self._player = player
        self._progress_scale.props.player = self._player

        self._player.connect('song-changed', self._update_view)
        self._player.connect(
            'notify::repeat-mode', self._on_repeat_mode_changed)
        self._player.connect('notify::state', self._sync_playing)

        repeat_mode = self._player.props.repeat_mode
        self._repeat_action.set_state(
            GLib.Variant("s", str(repeat_mode.value)))
        self._repeat_action.connect("activate", self._repeat_menu_changed)

        self._sync_repeat_image()

    def _repeat_menu_changed(
            self, action: Gio.SimpleAction, new_state: GLib.Variant) -> None:
        self._repeat_action.set_state(new_state)
        new_mode = new_state.get_string()
        self._player.props.repeat_mode = RepeatMode(int(new_mode))

    @Gtk.Template.Callback()
    def _on_progress_value_changed(self, progress_scale):
        seconds = int(progress_scale.get_value() / 60)
        self._progress_time_label.set_label(utils.seconds_to_string(seconds))

    @Gtk.Template.Callback()
    def _on_prev_button_clicked(self, button):
        self._player.previous()

    @Gtk.Template.Callback()
    def _on_play_button_clicked(self, button):
        self._player.play_pause()

    @Gtk.Template.Callback()
    def _on_next_button_clicked(self, button):
        self._player.next()

    def _on_repeat_mode_changed(self, klass, param):
        self._sync_repeat_image()
        self._sync_prev_next()

    def _sync_repeat_image(self) -> None:
        self._repeat_image.set_from_icon_name(
            self._player.props.repeat_mode.icon)

    def _sync_playing(self, player, state):
        if (self._player.props.state == Playback.STOPPED
                and not self._player.props.has_next
                and not self._player.props.has_previous):
            self.props.revealed = False
            return

        self.props.revealed = True

        if self._player.props.state == Playback.PLAYING:
            icon_name = "media-playback-pause-symbolic"
            tooltip = _("Pause")
        else:
            icon_name = "media-playback-start-symbolic"
            tooltip = _("Play")

        if self._play_pause_image.props.icon_name != icon_name:
            self._play_pause_image.props.icon_name = icon_name

        self._play_button.set_tooltip_text(tooltip)

    def _sync_prev_next(self):
        self._next_button.props.sensitive = self._player.props.has_next
        self._prev_button.props.sensitive = self._player.props.has_previous

    def _update_view(self, player):
        """Update all visual elements on song change

        :param Player player: The main player object
        """
        coresong = player.props.current_song
        self._duration_label.props.label = utils.seconds_to_string(
            coresong.props.duration)
        self._progress_time_label.props.label = "0:00"

        self._play_button.set_sensitive(True)
        self._sync_prev_next()

        artist = coresong.props.artist
        title = coresong.props.title

        self._title_label.props.label = title
        self._artist_label.props.label = artist

        self._tooltip.props.title = title
        self._tooltip.props.subtitle = artist

        self._cover_image.props.paintable.props.coreobject = coresong

    @Gtk.Template.Callback()
    def _on_tooltip_query(self, widget, x, y, kb, tooltip, data=None):
        tooltip.set_custom(self._tooltip)

        return True
