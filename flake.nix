{
  description = "Confidential computing packages";

  inputs.nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
  inputs.flake-utils.url = "github:numtide/flake-utils";
  inputs.nix-filter.url = "github:numtide/nix-filter";

  outputs = {
    self,
    nixpkgs,
    flake-utils,
    nix-filter,
  }: let
    system = "x86_64-linux";
    pkgs = import nixpkgs {
      inherit system;
      overlays = [nix-filter.overlays.default];
    };
    nix = import ./nix {
      inherit pkgs;
    };
  in {
    packages.${system} =
      flake-utils.lib.filterPackages system nix;

    overlays.default = _final: _prev: ((nix.lib.forAllPlatforms {
        inherit (self.packages.${system}) ccf ccf-sandbox lskv lskv-sandbox;
      })
      // {
        inherit (self.packages.${system}) openenclave az-dcap sgx-dcap;
      });

    checks.${system} =
      pkgs.lib.attrsets.filterAttrs
      (name: _value: name != "override" && name != "overrideDerivation")
      nix.ci-checks
      // {
        inherit (self.packages.${system}) lskv-sandbox-virtual lskv-sandbox-sgx;
      };

    lib = nix.lskvlib;

    formatter.${system} = pkgs.alejandra;

    apps.${system} = {
      ccf-sandbox-virtual = flake-utils.lib.mkApp {
        drv = self.packages.${system}.ccf-sandbox-virtual;
        exePath = "/bin/sandbox.sh";
      };
      ccf-sandbox-sgx = flake-utils.lib.mkApp {
        drv = self.packages.${system}.ccf-sandbox-sgx;
        exePath = "/bin/sandbox.sh";
      };

      lskv-sandbox-virtual = flake-utils.lib.mkApp {
        drv = self.packages.${system}.lskv-sandbox-virtual;
        exePath = "/bin/lskv-sandbox.sh";
      };
      lskv-sandbox-sgx = flake-utils.lib.mkApp {
        drv = self.packages.${system}.lskv-sandbox-sgx;
        exePath = "/bin/lskv-sandbox.sh";
      };

      oesign = flake-utils.lib.mkApp {
        drv = self.packages.${system}.openenclave;
        exePath = "/bin/oesign";
      };
    };

    devShells.${system}.default =
      pkgs.mkShell
      {
        packages = with pkgs;
          [
            clang-tools_10
            shellcheck
            nodePackages.npm
            nodejs
            cmake-format

            # for benchmarking
            python3Packages.pandas
            python3Packages.loguru
            python3Packages.seaborn
            python3Packages.paramiko
            jupyter

            # for go-ycsb
            go
          ]
          ++ [
            nix.python3.pkgs.cimetrics
          ];
        inputsFrom = [nix.lskv-virtual];
      };
  };
}
