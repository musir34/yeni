{pkgs}: {
  deps = [
    pkgs.nano
    pkgs.mailutils
    pkgs.zip
    pkgs.openssl
    pkgs.glibcLocales
    pkgs.postgresql
  ];
}
