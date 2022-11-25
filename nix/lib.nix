{lib}: rec {
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
}
