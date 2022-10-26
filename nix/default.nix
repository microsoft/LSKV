{
  pkgs,
  packageOverrides ? (self: super: {}),
}:
pkgs.lib.makeScope pkgs.newScope (self:
    rec {
      az-dcap = self.callPackage ./az-dcap.nix {};
      sgx-dcap = self.callPackage ./sgx-dcap.nix {};

      openenclave = self.callPackage ./openenclave.nix {
        # Openenclave doesn't build with libcxx, for some reason.
        stdenv = pkgs.llvmPackages_10.stdenv;
      };

      ccf = self.callPackage ./ccf.nix {
        stdenv = pkgs.llvmPackages_10.libcxxStdenv;
      };

      ccf-sandbox = self.callPackage ./ccf-sandbox.nix {};

      lskv = self.callPackage ./lskv.nix {
        stdenv = pkgs.llvmPackages_10.libcxxStdenv;
      };
      lskv-virtual = lskv;
      lskv-sgx = lskv.override {enclave = "sgx";};

      lskv-sandbox-virtual = self.callPackage ./lskv-sandbox.nix {enclave = "virtual";};
      lskv-sandbox-sgx = self.callPackage ./lskv-sandbox.nix {enclave = "sgx";};

      ci-checks = self.callPackage ./ci-checks.nix {};

      # A python3 derivation that is extended with some CC related
      # packages.
      python3 = pkgs.python3.override {
        packageOverrides = pself: psuper: {
          # Some generic python packages that are missing from
          # nixpkgs.
          columnar = pself.callPackage ./python/columnar.nix {};
          string-color = pself.callPackage ./python/string-color.nix {};
          adtk = pself.callPackage ./python/adtk.nix {};
          cimetrics = pself.callPackage ./python/cimetrics.nix {};
          better-exceptions = pself.callPackage ./python/better-exceptions.nix {};

          python-ccf = pself.callPackage ./python/python-ccf.nix {
            ccf = self.ccf;
          };
          python-ccf-infra = pself.callPackage ./python/python-ccf-infra.nix {};
        };
      };

      mkShell = args:
        (pkgs.mkShell.override {
          stdenv = pkgs.llvmPackages_10.libcxxStdenv;
        }) ({
            NIX_CFLAGS_COMPILE = "-Wno-unused-command-line-argument";
            NIX_NO_SELF_RPATH = "1";
          }
          // args);
    }
    // (pkgs.lib.attrsets.mapAttrs'
      (name: value: pkgs.lib.attrsets.nameValuePair ("ci-checks-" + name) value)
      (pkgs.callPackage ./ci-checks.nix {})))
