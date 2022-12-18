{
  buildPythonPackage,
  fetchPypi,
  columnar,
  colorama,
}:
buildPythonPackage rec {
  pname = "string-color";
  version = "1.2.3";
  src = fetchPypi {
    inherit pname version;
    hash = "sha256-wkksYmvXfKFovxOidS/tXPmI2HvdF4U723x6CwADwYM=";
  };
  propagatedBuildInputs = [
    columnar
    colorama
  ];
}
