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
import shutil as sh
import os
import sys

pqbuild_vstring = "1.1.0"
_uic_check_command = "--version"
_errmsg_source_does_not_exist = "[WARN] Source does not exist: \n\t%s"
_errmsg_ui_compiler_not_available = "[WARN] Compiler %s not found; skipping."
_errmsg_no_ui_forms_specified = "No UI forms specified."


class Builder(object):
    """Main class.

    Either call python pybuild.py path/to/buildspec.yaml
    or use Builder().run("path/to/buildspec.yaml").
    """

    def _excluder(self, dir, names):
        """Ignore method for shutil.copytree().

        Extended to accomodate for specific file/folder exclusion.
        """
        # Get list of files to be ignored by pattern rules:
        base = self._shutil_ignore(dir, names)
        # Append specific exclusion files, if any are in the current directory:
        if dir in self._excluded_folders:
            exclude = set([*base, *names])
        elif dir in self._excluded_files.keys():
            extra = [name for name in names if name in self._excluded_files[dir]]
            exclude = set([*base, *extra])
        else:
            exclude = base
        return exclude

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
        # === parse excludes
        # make shutil pattern ignorer
        try:
            patterns = self.spec["exclude"]["patterns"]
        except KeyError:
            patterns = list()
        self._shutil_ignore = sh.ignore_patterns(*patterns)
        if len(patterns) > 0:
            print("Excluding patterns: %s" % ", ".join(patterns))
        # parse specific exclusions:
        self._excluded_folders = list()
        self._excluded_files = dict()
        try:
            specific = self.spec["exclude"]["specific"]
        except KeyError:
            specific = list()
        if len(specific) > 0:
            print("Excluding specific: %s" % "\n\t".join(specific))
        for path in specific:
            if os.path.isdir(path):
                self._excluded_folders.append(path)
            else:
                dir, filename = os.path.split(path)
                try:
                    self._excluded_files[dir]
                except KeyError:
                    self._excluded_files[dir] = set()
                self._excluded_files[dir].add(filename)

    def _compile_form(self, form, outfile=None):
        """Compile a Qt .ui file "form", optionally to output file "outfile"."""
        if outfile is not None:
            out = outfile
        else:
            out = "%s_ui.py" % form.split(".ui")[0]
        print("Compiling form: %s --> %s" % (form, out))
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
                    self._compile_form(form)
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
                    sh.copytree(
                        source,
                        target,
                        ignore=self._excluder,
                        dirs_exist_ok=True,
                        copy_function=sh.copy)
                else:
                    if not os.path.isdir(target):
                        print("\tTarget directory does not exist; creating.")
                        os.mkdir(target)
                    sh.copy(source, target)
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
                sh.rmtree(target)
            # makedirs as needed
            os.makedirs(target, exist_ok=True)
            sh.copytree(
                "__TMP__", target,
                dirs_exist_ok=True, copy_function=sh.copy)
            print("Shipped to: %s" % target)

        for target in targets:
            ship_to(target)

    def build(self, specfile, clean=True):
        """Build."""
        self.parse_buildspec(specfile)
        self.compile_qt_forms()
        self.assemble()
        self.ship()
        if clean:
            self.clean()
        else:
            print("[WARN] Requested to not clean build directory (__TMP__).")
        print("======\nDone.")

    def clean(self):
        """Do post-build cleanup of tmp directory."""
        print("Cleaning tmp build directory...")
        sh.rmtree("__TMP__")


def main(builder_class=Builder):
    """Call when executing as script."""
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
    main()
