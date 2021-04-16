var auth2;
// Sign in function to pass the user info to session
/*
function onSignIn(googleUser){
    var id_token = googleUser.getAuthResponse().id_token;
    var form = document.createElement('form');
    var input = document.createElement("INPUT").setAttribute("type", "text");
    document.body.appendChild(form);
    form.method = 'post';
    form.action = "/login";
    form.appendChild(input);
    input.name = "idtoken";
    input.value = id_token;
    form.submit();
}
*/
function onSignIn(googleUser){
    var id_token = googleUser.getAuthResponse().id_token;
    var xhr = new XMLHttpRequest();
    xhr.open('POST', '/login');
    xhr.setRequestHeader('Content-Type', 'application/x-www-form-urlencoded');
    xhr.onload = function() {
        console.log('Signed in as: ' + googleUser.getBasicProfile().getName());
    };
    console.log(id_token);
    xhr.send('idtoken=' + id_token);
    redirectPost();
}

function redirectPost() {
    var form = document.querySelector("#redirect_post");
    form.submit();
}

/**
 * Initializes the Sign-In client.
 */
var initClient = function() {
    gapi.load('auth2', function(){
        /**
         * Retrieve the singleton for the GoogleAuth library and set up the
         * client.
         */
        auth2 = gapi.auth2.init({
            client_id: '698693736809-edhug0806akh4ba8slfgo01tnd3o3svg.apps.googleusercontent.com'
        });

        // Attach the click handler to the sign-in button
        auth2.attachClickHandler('signin-button', {}, onSuccess, onFailure);
    });
};

/**
 * Handle successful sign-ins.
 */
var onSuccess = function() {
    const id_token = sessionStorage.getItem('token');
    var xhr = new XMLHttpRequest();
    xhr.open('POST', '/login');
    xhr.setRequestHeader('Content-Type', 'application/x-www-form-urlencoded');
    xhr.send('idtoken=' + id_token);
 };

/**
 * Handle sign-in failures.
 */
var onFailure = function(error) {
    console.log(error);
};

// Logout function
function signOut() {
    var auth2 = gapi.auth2.getAuthInstance();
    auth2.signOut().then(function () {
      console.log('User signed out.');
    });
}

function onLoad() {
    gapi.load('auth2', function() {
      gapi.auth2.init();
    });
  }