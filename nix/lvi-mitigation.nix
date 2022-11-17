{
  fetchFromGitHub,
  fetchzip,
  stdenv,
  openenclave-version,
  openenclave-src,
  clang,
  gcc,
}: let
  intel-tarball = fetchzip {
    url = "https://download.01.org/intel-sgx/sgx-linux/2.13/as.ld.objdump.gold.r3.tar.gz";
    sha256 = "sha256-gD0LOLebDHZHrV7MW/ApqzdPxazidmDUDqBEnm1JmdQ=";
  };
in
  stdenv.mkDerivation {
    pname = "lvi-mitigation";
    version = openenclave-version;
    src = openenclave-src;
    patches = [patches/openenclave.diff];

    buildInputs = [clang gcc];

    preConfigure = ''
      patchShebangs scripts/lvi-mitigation/*

      ln -s ${intel-tarball} intel-tarball

      ./scripts/lvi-mitigation/install_lvi_mitigation_bindir
    '';

    dontBuild = true;
    dontInstall = true;
  }
