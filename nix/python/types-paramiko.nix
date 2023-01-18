{
  buildPythonPackage,
  fetchPypi,
  cryptography,
}:
buildPythonPackage rec {
  pname = "types-paramiko";
  version = "2.12.0.2";
  src = fetchPypi {
    inherit version;
    pname = "types-paramiko";
    hash = "sha256-p+uhgFYc9sNxMMos/BVavg9NSkbOQZ99HE65YgOdbzU=";
  };
  propagatedBuildInputs = [
    cryptography
  ];
  doCheck = false;
}
