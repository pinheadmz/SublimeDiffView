import re
import sublime

from .hunk_diff import HunkDiff, DummyHunkDiff
from ..util.constants import Constants


class FileDiff(object):
    """Representation of a single file's diff."""

    HUNK_MATCH = re.compile('\r?\n@@ \-(\d+),?(\d*) \+(\d+),?(\d*) @@')

    def __init__(self, filename, abs_filename, diff_text):
        """Constructor.

        Args:
            filename: The filename as given by Git - i.e. relative to the Git base directory.
            abs_filename: The absolute filename for this file.
            diff_text: The text of the Git diff.
        """
        self.filename = filename
        self.abs_filename = abs_filename
        self.old_file = 'UNDEFINED'
        self.new_file = 'UNDEFINED'
        self.diff_text = diff_text
        self.hunks = []

    def get_hunks(self, include_headers=False):
        """Get the changed hunks for this file.

        Wrapper to force parsing only once, and only when the hunks are required.
        """
        if not self.hunks:
            self.parse_diff(include_headers=include_headers)
        return self.hunks

    def parse_diff(self, include_headers=False):
        """Run the Git diff command, and parse the diff for this file into hunks.

        Do not call directly - use `get_hunks` instead.
        """
        hunks = self.HUNK_MATCH.split(self.diff_text)

        # First item is the diff header - drop it
        hunks.pop(0)
        match_len = 5
        while len(hunks) >= match_len:
            self.hunks.append(HunkDiff(self, hunks[:match_len]))
            hunks = hunks[match_len:]

        # This file has changes, add a dummy 'hunk' for the header, which is just
        # the start of the file.
        if include_headers:
            self.hunks.insert(0, DummyHunkDiff(self, len(self.hunks)))

    def add_regions(self, view, regions, styles):
        """Add all highlighted regions to the view for this file.

        Args:
            view: The view to add regions to.
            regions: The regions to add.
            styles: A map of styles for the diff region types.
        """
        view.add_regions(Constants.ADD_REGION_KEY, regions["ADD"], styles["ADD"], flags=Constants.ADD_REGION_FLAGS)
        view.add_regions(Constants.MOD_REGION_KEY, regions["MOD"], styles["MOD"], flags=Constants.MOD_REGION_FLAGS)
        view.add_regions(Constants.DEL_REGION_KEY, regions["DEL"], styles["DEL"], flags=Constants.DEL_REGION_FLAGS)

    def add_old_regions(self, view, styles):
        """Add all highlighted regions to the view for this (old) file.

        Args:
            view: The view to add regions to.
            styles: A map of styles for the diff region types.
        """
        regions = {}
        for sel in ["ADD", "MOD", "DEL"]:
            regions[sel] = [r for h in self.hunks for r in h.get_old_regions(view) if h.hunk_type == sel]
        self.add_regions(view, regions, styles)
        for h in self.hunks:
            if h.hunk_type == "ADD":
                region = sublime.Region(
                    view.text_point(h.old_line_start - 1, 0),
                    view.text_point(h.old_line_start - 1, 0))
                for _ in range(h.new_hunk_len):
                    view.add_phantom("", region, "<br style='line-height:0.9rem'>", sublime.LAYOUT_BLOCK)
            if h.hunk_type == "MOD":
                diff = h.new_hunk_len - h.old_hunk_len
                if diff > 0:
                    region = sublime.Region(
                        view.text_point(h.old_line_start + h.old_hunk_len - 2, 0),
                        view.text_point(h.old_line_start + h.old_hunk_len - 2, 0))
                    for _ in range(diff):
                        view.add_phantom("", region, "<br style='line-height:0.9rem'>", sublime.LAYOUT_BLOCK)

    def add_new_regions(self, view, styles):
        """Add all highlighted regions to the view for this (new) file.

        Args:
            view: The view to add regions to.
            styles: A map of styles for the diff region types.
        """
        regions = {}
        for sel in ["ADD", "MOD", "DEL"]:
            regions[sel] = [r for h in self.hunks for r in h.get_new_regions(view) if h.hunk_type == sel]
        self.add_regions(view, regions, styles)
        for h in self.hunks:
            if h.hunk_type == "DEL":
                region = sublime.Region(
                    view.text_point(h.new_line_start - 1, 0),
                    view.text_point(h.new_line_start - 1, 0))
                for _ in range(h.old_hunk_len):
                    view.add_phantom("", region, "<br style='line-height:0.9rem'>", sublime.LAYOUT_BLOCK)
            if h.hunk_type == "MOD":
                diff = h.old_hunk_len - h.new_hunk_len
                if diff > 0:
                    region = sublime.Region(
                        view.text_point(h.new_line_start + h.new_hunk_len - 2, 0),
                        view.text_point(h.new_line_start + h.new_hunk_len - 2, 0))
                    for _ in range(diff):
                        view.add_phantom("", region, "<br style='line-height:0.9rem'>", sublime.LAYOUT_BLOCK)
