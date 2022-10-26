{
  buildPythonPackage,
  fetchPypi,
  matplotlib,
  scikit-learn,
  pandas,
  statsmodels,
  tabulate,
}:
buildPythonPackage rec {
  pname = "adtk";
  version = "0.6.2";
  src = fetchPypi {
    inherit pname version;
    hash = "sha256-bPr7RLWtJqL/1kCut52E/FOD0tQsl6R0IGlbrb7ie+g=";
  };
  propagatedBuildInputs = [
    matplotlib
    scikit-learn
    pandas
    statsmodels
    tabulate
  ];
}
