{
  runCommand,
  writeShellScriptBin,
  shellcheck,
  nodePackages,
  python3Packages,
  cpplint,
  alejandra,
  deadnix,
  statix,
  shfmt,
  cmake-format,
  python-ccf,
  types-paramiko,
}: let
  pythonDeps = with python3Packages; [
    loguru
    httpx
    pandas
    seaborn
    pytest
    typing-extensions
    types-protobuf
    python-ccf
    paramiko
    types-paramiko
  ];
in {
  checks = {
    shellcheck =
      runCommand "shellcheck"
      {
        buildInputs = [shellcheck];
      } ''
        find ${../.} -name '*.sh' ! -name "3rdparty" | xargs shellcheck -s bash -e SC2044,SC2002,SC1091,SC2181
        mkdir $out
      '';

    cmake-format =
      runCommand "cmake-format"
      {
        buildInputs = [cmake-format];
      } ''
        find ${../.} -name '*.cmake' -name '*.CMakeLists.txt' ! -name "3rdparty" | xargs cmake-format --check
        mkdir $out
      '';

    prettier =
      runCommand "prettier"
      {
        buildInputs = [nodePackages.prettier];
      } ''
        for e in ts js md yaml yml json; do
          find ${../.} -name "*.$e" ! -name "3rdparty" | xargs prettier --check
        done
        mkdir $out
      '';

    black =
      runCommand "black"
      {
        buildInputs = [python3Packages.black];
      } ''
        find ${../.} -name '*.py' ! -name "3rdparty" | xargs black --check
        mkdir $out
      '';

    pylint =
      runCommand "pylint"
      {
        buildInputs = [python3Packages.pylint] ++ pythonDeps;
      } ''
        find ${../.} -name '*.py' ! -name "3rdparty" | xargs pylint --ignored-modules "*_pb2"
        mkdir $out
      '';

    mypy =
      runCommand "mypy"
      {
        buildInputs = [python3Packages.mypy] ++ pythonDeps;
      } ''
        find ${../.} -name '*.py' ! -name "3rdparty" | xargs mypy
        mkdir $out
      '';

    cpplint =
      runCommand "cpplint"
      {
        buildInputs = [cpplint];
      } ''
        cpplint --filter=-whitespace/braces,-whitespace/indent,-whitespace/comments,-whitespace/newline,-build/include_order,-build/include_subdir,-runtime/references,-runtime/indentation_namespace ${../.}/src/**/*.cpp ${../.}/src/**/*.h
        mkdir $out
      '';

    nixfmt =
      runCommand "nixfmt"
      {
        buildInputs = [alejandra];
      } ''
        alejandra --check ${../.}/**/*.nix
        mkdir $out
      '';

    deadnix =
      runCommand "deadnix"
      {
        buildInputs = [deadnix];
      } ''
        deadnix --fail ${../.}
        mkdir $out
      '';

    statix =
      runCommand "statix"
      {
        buildInputs = [statix];
      } ''
        statix check ${../.}
        mkdir $out
      '';

    shfmt =
      runCommand "shfmt" {}
      ''
        find ${./.} -name '*.sh' ! -name "3rdparty" | xargs ${shfmt}/bin/shfmt --diff --simplify --case-indent --indent 2
        mkdir $out
      '';
  };
  fixes = {
    prettier =
      writeShellScriptBin "prettier"
      ''
        git ls-files -- . ':!:3rdparty/' | grep -e '\.ts$' -e '\.js$' -e '\.md$' -e '\.yaml$' -e '\.yml$' -e '\.json$' | xargs ${nodePackages.prettier}/bin/prettier --write
      '';

    black =
      writeShellScriptBin "black"
      ''
        git ls-files -- . ':!:3rdparty/' | grep -e '\.py$' | xargs ${python3Packages.black}/bin/black
      '';

    nixfmt =
      writeShellScriptBin "nixfmt"
      ''
        git ls-files -- . ':!:3rdparty/' | grep -e '\.nix$' | xargs ${alejandra}/bin/alejandra
      '';

    shfmt =
      writeShellScriptBin "shfmt"
      ''
        git ls-files -- . ':!:3rdparty/' | grep -e '\.sh$'| xargs ${shfmt}/bin/shfmt --write --simplify --case-indent --indent 2
      '';

    cmake-format =
      writeShellScriptBin "cmake-format"
      ''
        git ls-files -- . ':!:3rdparty/' | grep -e '\.cmake$' -e '^CMakeLists.txt' | xargs ${cmake-format}/bin/cmake-format --in-place
      '';

    statix =
      writeShellScriptBin "statix"
      ''
        ${statix}/bin/statix fix .
      '';
  };
}
