{
  pkgs,
  packageOverrides ? (_self: _super: {}),
}:
pkgs.lib.makeScope pkgs.newScope (
  self: let
    lskvlib =
      pkgs.callPackage ./lib.nix {};

    # A python3 derivation that is extended with some CC related
    # packages.
    python3 = pkgs.python3.override {
      packageOverrides = pself: _psuper: {
        # Some generic python packages that are missing from
        # nixpkgs.
        columnar = pself.callPackage ./python/columnar.nix {};
        string-color = pself.callPackage ./python/string-color.nix {};
        adtk = pself.callPackage ./python/adtk.nix {};
        pycose = pself.callPackage ./python/pycose.nix {};
        cimetrics = pself.callPackage ./python/cimetrics.nix {};
        better-exceptions = pself.callPackage ./python/better-exceptions.nix {};

        types-paramiko = pself.callPackage ./python/types-paramiko.nix {};

        python-ccf = pself.callPackage ./python/python-ccf.nix {inherit ccf;};
        python-ccf-infra = pself.callPackage ./python/python-ccf-infra.nix {};
      };
    };

    ccf = self.callPackage ./ccf.nix {
      stdenv = pkgs.llvmPackages_16.libcxxStdenv;
    };
    ccf-sandbox = self.callPackage ./ccf-sandbox.nix {inherit ccf;};
    lskv = self.callPackage ./lskv.nix {
      inherit ccf;
      stdenv = pkgs.llvmPackages_16.libcxxStdenv;
    };
    lskv-sandbox = self.callPackage ./lskv-sandbox.nix {inherit ccf-sandbox lskv;};
    packages = lskvlib.forAllPlatforms {
      inherit ccf ccf-sandbox lskv lskv-sandbox;
      ccf-sandbox-verbose = ccf-sandbox.override {
        verbose = true;
      };
      lskv-sandbox-verbose = lskv-sandbox.override {
        verbose = true;
      };
    };
    ci-checks-pkgs = pkgs.callPackage ./ci-checks.nix {inherit (python3.pkgs) python-ccf types-paramiko;};
    ci-checks = lskvlib.ciChecks ci-checks-pkgs.checks;
    ci-fixes = lskvlib.ciFixes ci-checks-pkgs.fixes;
  in
    rec {
      inherit lskvlib ci-checks ci-fixes python3;
      inherit (python3.pkgs) python-ccf;

      ci-check-all = lskvlib.ciChecksAll ci-checks-pkgs.checks;
      ci-fix-all = lskvlib.ciFixesAll ci-checks-pkgs.fixes;

      az-dcap = self.callPackage ./az-dcap.nix {};
      sgx-dcap = self.callPackage ./sgx-dcap.nix {};

      openenclave-version = "0.19.3";
      openenclave-src = pkgs.fetchFromGitHub {
        owner = "openenclave";
        repo = "openenclave";
        rev = "v${openenclave-version}";
        hash = "sha256-RN7Mq6RO09CZOEoi/nYpPfa7TT1I5FYKqET8wRXnIxU=";
        fetchSubmodules = true;
      };
      lvi-mitigation = self.callPackage ./lvi-mitigation.nix {};
      openenclave = self.callPackage ./openenclave.nix {
        stdenv = pkgs.llvmPackages_11.libcxxStdenv;
        openssl = pkgs.openssl_1_1;
      };

      k6 = self.callPackage ./k6.nix {};

      mkShell = args:
        (pkgs.mkShell.override {
          stdenv = pkgs.llvmPackages_16.libcxxStdenv;
        }) ({
            NIX_CFLAGS_COMPILE = "-Wno-unused-command-line-argument";
            NIX_NO_SELF_RPATH = "1";
          }
          // args);
    }
    // ci-checks
    // ci-fixes
    // packages
)
