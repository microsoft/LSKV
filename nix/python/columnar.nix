{
  buildPythonPackage,
  fetchPypi,
  wcwidth,
  toolz,
}:
buildPythonPackage rec {
  pname = "columnar";
  version = "1.4.1";
  src = fetchPypi {
    inherit version;
    pname = "Columnar";
    hash = "sha256-w8tXJzMzsv+c+q/IbwkwdBkzDJf6qI3P4j3wXm+7nHI=";
  };
  propagatedBuildInputs = [
    wcwidth
    toolz
  ];
  doCheck = false;
}
