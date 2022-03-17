# Copyright 2021 Anton Douginets

# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#   http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""PyBuild: a build script for the Python/Qt (PySide6) stack."""

import yaml
import shutil
import os
import sys

pqbuild_vstring = "1.2.0"
_uic_check_command = "--version"
_errmsg_source_does_not_exist = "[WARN] Source does not exist: \n\t%s"
_errmsg_ui_compiler_not_available = "[WARN] Compiler %s not found; skipping."
_errmsg_no_ui_forms_specified = "No UI forms specified."


def copytree_ignore(ignore_patterns=[], ignore_specific=[]):
    """Make a copytree compatible ignore method.

    Different from shutil.copytree compatible ignore callables
    in that it can also indicate that the entire directory is to be omitted.
    """
    get_ignored_by_pattern = shutil.ignore_patterns(*ignore_patterns)
    abs_ignore_list = [os.path.abspath(item) for item in ignore_specific]

    def get_ignored(path, names):
        ignored = get_ignored_by_pattern(path, names)
        for name in names:
            if os.path.abspath(os.path.join(path, name)) in abs_ignore_list:
                ignored.add(name)
        return ignored

    return get_ignored


def copytree(src, dst, ignore=None, exist_ok=True):
    """Copy directory tree from "src" to "dst".

    Works as (bash) "cp -r src/* dst/".

    Parameters:
        src:
            directory to copy from
        dst:
            directory to copy to
    """
    names = os.listdir(src)
    os.makedirs(dst, exist_ok=exist_ok)
    if ignore is None:
        ignored = set()
    else:
        ignored = ignore(src, names)
    for name in names:
        srcname = os.path.join(src, name)
        dstname = os.path.join(dst, name)
        if name in ignored:
            continue
        elif os.path.isdir(srcname):
            copytree(srcname, dstname, ignore=ignore, exist_ok=exist_ok)
        else:
            shutil.copy2(srcname, dstname)


class Builder(object):
    """Main class.

    Either call python pybuild.py path/to/buildspec.yaml
    or use Builder().run("path/to/buildspec.yaml").
    """

    def parse_buildspec(self, specfile):
        """Parse specfile and initialize the Builder."""
        # load specfile
        print("pqbuild v. %s" % pqbuild_vstring)
        if not os.path.isfile(specfile):
            raise FileNotFoundError("Specfile not found: %s" % specfile)
        else:
            with open(specfile, "r") as spec:
                self.spec = yaml.safe_load(spec)
            print("Loaded buildspec: %s" % specfile)
        print("======\nBuilding %s v. %s..." % (
            self.spec["build"]["name"],
            self.spec["build"]["vstring"]))
        # move to build root
        print("Build root: %s" % self.spec["build"]["root"])
        os.chdir(self.spec["build"]["root"])
        # make tmp dir
        if os.path.isdir("__TMP__"):
            print("[WARN] TMP directory exists!")
            self.clean()
        os.mkdir("__TMP__")
        # parse excludes - patterns
        try:
            patterns = self.spec["exclude"]["patterns"]
        except KeyError:
            patterns = list()
        if len(patterns) > 0:
            print("Excluding patterns: %s" % ", ".join(patterns))
        # parse excludes - specific:
        try:
            specific = self.spec["exclude"]["specific"]
        except KeyError:
            specific = list()
        if len(specific) > 0:
            print("Excluding specific:\n\t%s" % "\n\t".join(specific))
        # make excluder
        self.copytree_excluder = copytree_ignore(
            ignore_patterns=patterns,
            ignore_specific=specific)

    def compile_qt_form(self, form, outfile=None):
        """Compile a Qt .ui file "form", optionally to output file "outfile"."""
        if outfile is not None:
            out = outfile
        else:
            out = "%s_ui.py" % form.split(".ui")[0]
        cmd = "%s -g python -o %s %s" % (
            self.spec["qt"]["compiler"], out, form)
        os.system(cmd)

    def compile_qt_forms(self):
        """Compile Qt UI forms, if asked."""
        try:
            qt = self.spec["qt"]
            forms = qt["forms"]
        except KeyError:
            print(_errmsg_no_ui_forms_specified)  # not asked
        else:
            print("------")
            check = os.system("%s %s" % (
                qt["compiler"], _uic_check_command)) == 0
            if check:
                for form in forms:
                    out = "%s_ui.py" % form.split(".ui")[0]
                    print("Compiling form: %s --> %s" % (form, out))
                    self.compile_qt_form(form, outfile=out)
            else:
                print(_errmsg_ui_compiler_not_available % qt["compiler"])

    def assemble(self):
        """Pack things into tmp dir, obeying exclusion rules."""
        print("------")
        print("Assembling...")
        # throw error if nothing to do lel
        try:
            include = self.spec["include"]
        except KeyError:
            raise Exception("No includes specified!")
        # otherwise
        for source in include.keys():
            target = os.path.join("__TMP__", include[source])
            if os.path.exists(source):
                print("Source: %s/ --> %s/" % (source, include[source]))
                if os.path.isdir(source):
                    copytree(source, target, ignore=self.copytree_excluder)
                else:
                    if not os.path.isdir(target):
                        print("\tTarget directory does not exist, creating.")
                        os.mkdir(target)
                    shutil.copy2(source, target)
            else:
                print(_errmsg_source_does_not_exist % source)

    def ship(self):
        """Ship the build to target."""
        print("------")
        targets = self.spec["build"]["target"]
        if isinstance(targets, list):
            pass
        else:
            targets = [targets]

        def ship_to(target):
            # if target exists, clean
            if os.path.isdir(target):
                print("Target exists, cleaning...")
                shutil.rmtree(target)
            # makedirs as needed
            shutil.copytree("__TMP__", target)
            print("Shipped to: %s" % target)

        for target in targets:
            ship_to(target)

    def build(self, specfile):
        """Build."""
        self.parse_buildspec(specfile)
        self.compile_qt_forms()
        self.assemble()
        self.ship()
        self.clean()
        print("======\nDone.")

    def clean(self):
        """Do post-build cleanup of tmp directory."""
        print("Cleaning tmp build directory...")
        shutil.rmtree("__TMP__")


def run(builder_class=Builder):
    """Execute build.

    Optionally specify a different builder class, e.g., to add extra steps.
    """
    N = len(sys.argv) - 1
    if N == 0:
        print("No buildspec file specified!")
    elif N == 1:
        specfile = sys.argv[1].strip()
    else:
        echo = ""
        for arg in sys.argv:
            echo += "%s " % str(arg)
        print("Didn't understand buildspec: %s" % echo)
    builder_class().build(specfile)


if __name__ == '__main__':
    run()
