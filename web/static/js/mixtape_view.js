const title = document.getElementById("newTitle");
const editTitleButton = document.getElementById("editTitle");
const confirmTitleButton = document.getElementById("confirmEditTitle");

editTitleButton.addEventListener("click", function() {
    title.disabled = false;
    title.focus();
    var length = title.value.length
    title.setSelectionRange(length, length);
    editTitleButton.hidden = true;
    confirmTitleButton.hidden = false;
} );

const art = document.getElementById("newArt");
const editArtButton = document.getElementById("editArt");
const confirmArtButton = document.getElementById("confirmEditArt");

editArtButton.addEventListener("click", function() {
    art.disabled = false;
    art.focus();
    var length = art.value.length
    art.setSelectionRange(length, length);
    editArtButton.hidden = true;
    confirmArtButton.hidden = false;
} );
