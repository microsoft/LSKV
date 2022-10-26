{
  runCommand,
  writeShellScriptBin,
  shellcheck,
  nodePackages,
  python3Packages,
  cpplint,
  alejandra,
}: {
  shellcheck =
    runCommand "shellcheck"
    {
      buildInputs = [shellcheck];
    } ''
      find ${../.} -name '*.sh' ! -name "3rdparty" | xargs shellcheck -s bash -e SC2044,SC2002,SC1091,SC2181
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

  prettier-fix =
    writeShellScriptBin "prettier"
    ''
      git ls-files -- . ':!:3rdparty/' | grep -e '\.ts$' -e '\.js$' -e '\.md$' -e '\.yaml$' -e '\.yml$' -e '\.json$' | xargs npx ${nodePackages.prettier}/bin/prettier --write
    '';

  black =
    runCommand "black"
    {
      buildInputs = [python3Packages.black];
    } ''
      find ${../.} -name '*.py' ! -name "3rdparty" | xargs black --check
      mkdir $out
    '';

  black-fix =
    writeShellScriptBin "black"
    ''
      git ls-files -- . ':!:3rdparty/' | grep -e '\.py$' | xargs ${python3Packages.black}/bin/black
    '';

  pylint =
    runCommand "pylint"
    {
      buildInputs = [python3Packages.pylint python3Packages.pandas python3Packages.seaborn python3Packages.setuptools];
    } ''
      find ${../.} -name '*.py' ! -name "3rdparty" | xargs pylint --ignored-modules "*_pb2"
      mkdir $out
    '';

  mypy =
    runCommand "mypy"
    {
      buildInputs = [python3Packages.mypy];
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

  nixfmt-fix =
    writeShellScriptBin "nixfmt"
    ''
      git ls-files -- . ':!:3rdparty/' | grep -e '\.nix$' | xargs ${alejandra}/bin/alejandra
    '';
}
