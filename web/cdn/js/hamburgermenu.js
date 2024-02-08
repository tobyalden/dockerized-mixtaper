function toggleHamburgerMenu() {
  var x = document.getElementById("hamburger-menu-items");
  if (x.style.display === "none") {
      x.style.display = "flex";
    } else {
    x.style.display = "none";
  }
}
