{ buildPythonPackage
, fetchPypi
}:
buildPythonPackage rec {
  pname = "better-exceptions";
  version = "0.2.1";
  src = fetchPypi {
    inherit version;
    pname = "better_exceptions";
    hash = "sha256-CnPv75a0j4Z+qYAiesOwDTapJ1Tm0xatLuRy8TYBRYA=";
  };
  doCheck = false;
}
