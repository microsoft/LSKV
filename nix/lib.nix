{
  lib,
  symlinkJoin,
  writeShellScriptBin,
}: rec {
  # the list of supported platforms we can build for
  platforms = ["virtual" "sgx" "snp"];

  # create a set of per-platform derivations with the name "$pkgname-$platform"
  forPlatform = platform: pkgs:
    lib.attrsets.mapAttrs' (name: value: lib.attrsets.nameValuePair "${name}-${platform}" (value.override {inherit platform;})) pkgs;

  # generate a set of derivations for each platform
  forPlatforms = platforms: pkgs:
    lib.lists.foldl' lib.trivial.mergeAttrs {} (
      map (platform: forPlatform platform pkgs) platforms
    );

  # generate a set of derivations for all supported platforms
  forAllPlatforms = forPlatforms platforms;

  ciChecks = pkgs:
    lib.attrsets.mapAttrs' (name: value: lib.attrsets.nameValuePair "ci-check-${name}" value) pkgs;

  ciFixes = pkgs:
    lib.attrsets.mapAttrs' (name: value: lib.attrsets.nameValuePair "ci-fix-${name}" value) pkgs;

  ciChecksAll = pkgs: let
    ci-checks = ciChecks pkgs;
  in
    symlinkJoin {
      name = "ci-check-all";
      paths = lib.attrsets.attrValues ci-checks;
    };

  ciFixesAll = pkgs: let
    ci-fixes = ciFixes pkgs;
    ci-fix-all-pkgs = symlinkJoin {
      name = "ci-fix-all";
      paths = lib.attrsets.attrValues ci-fixes;
    };
  in
    writeShellScriptBin "ci-fix-all" ''
      for bin in ${ci-fix-all-pkgs}/bin/*; do
          echo "Running $bin"
          $bin
      done
    '';
}
