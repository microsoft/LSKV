{ buildPythonPackage
, fetchFromGitHub
, matplotlib
, GitPython
, requests
, pythonRelaxDepsHook
, adtk
, pyparsing
, pyyaml
, pymongo
, azure-storage-blob
}:
buildPythonPackage {
  pname = "cimetrics";
  version = "0.3.12";
  src = fetchFromGitHub {
    owner = "jumaffre";
    repo = "cimetrics";
    rev = "d6647e7f1018ff18e9e9c457851d50e555870e8e";
    hash = "sha256-h+/Got2InF9Vfv3hXguL8kq3gfR50jcv9u8YFsKMkKA=";
  };

  propagatedBuildInputs = [
    matplotlib
    GitPython
    requests
    adtk
    pyparsing
    pyyaml
    pymongo
    azure-storage-blob
  ];

  nativeBuildInputs = [ pythonRelaxDepsHook ];
  pythonRelaxDeps = [ "pyparsing" ];

  doCheck = false;
}
