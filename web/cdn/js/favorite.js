function toggleHeart(id) {
    var favDiv = document.getElementById(id);
    var heart = favDiv.getElementsByTagName("i")[0]
    heart.classList.toggle("fa-regular");
    heart.classList.toggle("fa-solid");
}

function favoriteMixtape(e, id) {
    e.preventDefault()
    toggleHeart(id);
    mixtapeId = id.split("-")[1]
    $.ajax({
      url: "/favorite",
      data: {
        mixtape_id: mixtapeId
      },
      success: function( result ) {
          console.log("Favorited (or unfavorited) mixtape!");
      },
      error: function() {
          console.log("Couldn't favorite (or unfavorite) mixtape");
          // Toggle back on failure
          toggleHeart(id);
      }
    });
}
