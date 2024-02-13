function favoriteMixtape(id) {
    var favDiv = document.getElementById(id);
    var heart = favDiv.getElementsByTagName("i")[0]
    heart.classList.toggle("fa-regular");
    heart.classList.toggle("fa-solid");
    //debugger;
}
