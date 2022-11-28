{
  buildGoModule,
  fetchFromGitHub,
  go,
}:
buildGoModule {
  name = "k6";
  version = "head";
  src = fetchFromGitHub {
    owner = "grafana";
    repo = "k6";
    rev = "2fe2dd32b3827eeeeb3959aff63a6b402aab0a5a";
    sha256 = "sha256-Y5s4w2yKwGu7nfegQUk14VbQiiU5Iv/GAme9LKhL3i0=";
  };

  patches = [
    ../patches/k6-micro.diff
  ];

  vendorSha256 = null;

  subPackages = ["./"];
}
