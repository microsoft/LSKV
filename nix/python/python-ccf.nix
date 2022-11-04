{
  buildPythonPackage,
  string-color,
  loguru,
  cryptography,
  ccf,
  pythonRelaxDepsHook,
}: let
  ccf-virtual = ccf {enclave = "virtual";};
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

    propagatedBuildInputs = [
      string-color
      loguru
      cryptography
    ];

    # Tests don't run, seems to be a problem with cryptography version pin.
    # CCF doesn't have any python tests anyway.
    doCheck = false;
  }
