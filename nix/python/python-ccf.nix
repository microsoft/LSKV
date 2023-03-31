{
  buildPythonPackage,
  string-color,
  loguru,
  cryptography,
  pycose,
  ccf,
  pythonRelaxDepsHook,
}: let
  ccf-virtual = ccf.override {platform = "virtual";};
in
  buildPythonPackage {
    inherit (ccf-virtual) version src;
    pname = "ccf";

    # ccf wants cryptography 37, but we only have 36.
    nativeBuildInputs = [pythonRelaxDepsHook];
    pythonRelaxDeps = ["cryptography"];

    preConfigure = ''
      cd python
      cat > version.py <<EOF
      CCF_VERSION = "$version"
      EOF
    '';

    patches = [
      ../patches/crypto39.diff
    ];

    propagatedBuildInputs = [
      string-color
      loguru
      cryptography
      pycose
    ];

    # Tests don't run, seems to be a problem with cryptography version pin.
    # CCF doesn't have any python tests anyway.
    doCheck = false;
  }
