import re
import sublime

from .diff_region import DiffRegion


class HunkDiff(object):

    NEWLINE_MATCH = re.compile('\r?\n')
    ADD_LINE_MATCH = re.compile('^\+(.*)')
    DEL_LINE_MATCH = re.compile('^\-(.*)')
    UNMERGED = 0
    MERGED_RIGHT = 1
    MERGED_LEFT = -1
    """Representation of a single 'hunk' from a Git diff.

    Args:
        file_diff: The parent `FileDiff` object.
        match: The match parts of the hunk header.
    """

    def __init__(self, file_diff, match):
        self.file_diff = file_diff
        self.old_regions = []
        self.new_regions = []
        self.old_line_focus = -1
        self.new_line_focus = -1
        self.full_old_region = None
        self.full_new_region = None
        self.merge_state = self.UNMERGED

        # Matches' meanings are:
        # - 0: start line in old file
        self.old_line_start = int(match[0])
        # - 1: num lines removed from old file (0 for ADD, missing if it's a
        #      one-line change)
        self.old_hunk_len = 1
        if len(match[1]) > 0:
            self.old_hunk_len = int(match[1])
        # - 2: start line in new file
        self.new_line_start = int(match[2])
        # - 3: num lines added to new file (0 for DEL, missing if it's a
        #      one-line change)
        self.new_hunk_len = 1
        if len(match[3]) > 0:
            self.new_hunk_len = int(match[3])
        # - 4: the remainder of the hunk, after the header
        self.context = self.NEWLINE_MATCH.split(match[4])[0]
        self.hunk_diff_lines = self.NEWLINE_MATCH.split(match[4])[1:]

        # Parse the diff
        self.add_lines = 0
        self.del_lines = 0
        self.parse_diff()
        if self.del_lines == 0:
            self.hunk_type = "ADD"
            plus_minus = "{}+".format(self.add_lines)
        elif self.add_lines == 0:
            self.hunk_type = "DEL"
            plus_minus = "{}-".format(self.del_lines)
        else:
            self.hunk_type = "MOD"
            plus_minus = "{}+/{}-".format(self.add_lines, self.del_lines)

        # Create the hunk description that will appear in the change list view
        self.oneline_description = "{:40} {:60} {}".format(
            "{} : {}".format(self.file_diff.filename, self.new_line_focus),
            self.context,
            plus_minus)
        # Create the hunk description that will appear in the quick_panel
        self.description = [
            "{} : {}".format(self.file_diff.filename, self.new_line_focus),
            self.context,
            "{} | {}{}".format(self.add_lines + self.del_lines,
                               "+" * self.add_lines,
                               "-" * self.del_lines)]

    def parse_diff(self):
        """Generate representations of the changed regions."""
        old_cur_line = self.old_line_start
        new_cur_line = self.new_line_start
        new_add_start = 0
        old_del_start = 0
        in_add = False
        in_del = False

        # Add a dummy blank line to catch regions going right to the end of the
        # hunk.
        for line in self.hunk_diff_lines + [' ']:
            if in_add and not line.startswith('+'):
                # ADD region ends.
                self.new_regions.append(DiffRegion(
                    "ADD",
                    new_add_start,
                    0,
                    new_cur_line,
                    0))
                in_add = False
            if in_del and not line.startswith('-'):
                # DEL region ends.
                self.old_regions.append(DiffRegion(
                    "DEL",
                    old_del_start,
                    0,
                    old_cur_line,
                    0))
                in_del = False

            if line.startswith('+'):
                self.add_lines += 1
                if not in_add:
                    new_add_start = new_cur_line
                    in_add = True
            elif line.startswith('-'):
                self.del_lines += 1
                if not in_del:
                    old_del_start = old_cur_line
                    in_del = True

            # If we've just found the first interesting part, that's where the
            # focus should be for this hunk.
            if not line.startswith(' '):
                if self.old_line_focus == -1:
                    self.old_line_focus = old_cur_line
                if self.new_line_focus == -1:
                    self.new_line_focus = new_cur_line

            # End of that line.
            if not line.startswith('+'):
                old_cur_line += 1
            if not line.startswith('-'):
                new_cur_line += 1

    def filespecs(self):
        """Get the portion of code that this hunk refers to in the format
        `(old_filename:old_line, new_filename:new_line)`.
        """
        old_filespec = "{}:{}".format(
            self.file_diff.old_file,
            self.old_line_focus)
        new_filespec = "{}:{}".format(
            self.file_diff.new_file,
            self.new_line_focus)
        return (old_filespec, new_filespec)

    def get_old_regions(self, view):
        """Create a `sublime.Region` for each (old) part of this hunk.

        Args:
            view: The view to create regions in.
        """
        if not self.full_old_region:
            self.full_old_region = sublime.Region(
                view.text_point(self.old_line_start-1, 0),
                view.text_point(self.old_line_start+self.old_hunk_len-1, 0))
            self.full_old_text = view.substr(self.full_old_region)
        return [sublime.Region(
            view.text_point(r.start_line - 1, r.start_col),
            view.text_point(r.end_line - 1, r.end_col))
            for r in self.old_regions]

    def get_new_regions(self, view):
        """Create a `sublime.Region` for each (new) part of this hunk.

        Args:
            view: The view to create regions in.
        """
        if not self.full_new_region:
            self.full_new_region = sublime.Region(
                view.text_point(self.new_line_start-1, 0),
                view.text_point(self.new_line_start+self.new_hunk_len-1, 0))
            self.full_new_text = view.substr(self.full_new_region)
        return [sublime.Region(
            view.text_point(r.start_line - 1, r.start_col),
            view.text_point(r.end_line - 1, r.end_col))
            for r in self.new_regions]

    def merge_valid(self, direction):
        """Is it valid to merge this hunk in the given direction?

        Args:
            direction: The direction of the merge.

        Returns:
            Whether the merge is valid.
        """
        if self.merge_state == self.UNMERGED:
            return True
        elif self.merge_state == self.MERGED_LEFT and direction == 'right':
            return True
        elif self.merge_state == self.MERGED_RIGHT and direction == 'left':
            return True
        return False

    def merge_changing_view(self, direction):
        """Pick the view that's actually going to change from this merge.

        Doesn't check whether the merge is actually valid - use `merge_valid`
        to check that.

        Args:
            direction: The direction of the merge ('right' or 'left').

        Returns:
            'right' or 'left'.
        """
        if direction == 'right':
            if self.merge_state == self.MERGED_LEFT:
                return 'left'
            else:
                return 'right'
        else:
            if self.merge_state == self.MERGED_RIGHT:
                return 'right'
            else:
                return 'left'

    def merge(self, view, edit, direction):
        """Perform the merge of this hunk.

        Args:
            view: The view that's changing.
            edit: The edit for that view.
            direction: The direction of the merge.
        """
        if direction == 'right':
            text = self.full_old_text
        else:
            text = self.full_new_text
        if self.merge_changing_view(direction) == 'right':
            region = self.full_new_region
        else:
            region = self.full_old_region

        view.replace(edit, region, text)

        # Update this hunk's state
        if direction == 'right':
            self.merge_state += 1
        else:
            self.merge_state -= 1

        # @@@ Update the full_new_region or full_old_region
