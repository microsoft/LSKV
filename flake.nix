{
  description = "Confidential computing packages";

  inputs.nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
  inputs.flake-utils.url = "github:numtide/flake-utils";

  outputs = { self, nixpkgs, flake-utils }:
    let
      system = "x86_64-linux";
      pkgs = import nixpkgs {
        system = system;
      };
    in
    {
      packages.${system} = flake-utils.lib.filterPackages system (import ./nix {
        inherit pkgs;
      });

      checks.${system} = pkgs.lib.attrsets.filterAttrs
        (name: value: name != "override" && name != "overrideDerivation")
        (import ./nix {
          inherit pkgs;
        }).ci-checks;

      apps.${system} = {
        ccf-sandbox = flake-utils.lib.mkApp {
          drv = self.packages.${system}.ccf-sandbox;
          exePath = "/bin/sandbox.sh";
        };
      };

      devShells.${system}.default = pkgs.mkShell {
        packages = with pkgs; [
          rnix-lsp
          nixpkgs-fmt
        ];
      };
    };
}
