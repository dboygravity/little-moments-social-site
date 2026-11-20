const postList = document.querySelector("#post-list");
const postForm = document.querySelector("#post-form");
const postMessage = document.querySelector("#post-message");
const fileInput = document.querySelector("#image");
const fileName = document.querySelector("#file-name");
const profileNav = document.querySelector("#profile-nav");
const composerAvatar = document.querySelector("#composer-avatar");
const feedStatus = document.querySelector("#feed-status");
const signedInName = document.querySelector("#signed-in-name");
let currentUser;
let csrfToken;

function avatarPath(filename) {
    return `/media/${encodeURIComponent(filename)}`;
}

async function apiRequest(url, options = {}) {
    const requestOptions = { ...options, headers: { ...(options.headers || {}) } };
    if (["POST", "PUT", "PATCH", "DELETE"].includes(requestOptions.method)) {
        requestOptions.headers["X-CSRF-Token"] = csrfToken;
    }
    const response = await fetch(url, requestOptions);
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || "Something went wrong. Please try again.");
    return data;
}

function setMessage(element, message, type = "") {
    element.textContent = message;
    element.className = `form-message ${type}`.trim();
}

function makeElement(tag, className, text) {
    const element = document.createElement(tag);
    if (className) element.className = className;
    if (text !== undefined) element.textContent = text;
    return element;
}

function formatDate(value) {
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return "";
    return date.toLocaleString([], { dateStyle: "medium", timeStyle: "short" });
}

async function renderComments(postCard, post) {
    const commentsBox = postCard.querySelector(".comments");
    try {
        const comments = await apiRequest(`/api/posts/${post.post_id}/comments`);
        commentsBox.replaceChildren();
        comments.forEach((comment) => {
            const line = makeElement("p", "comment");
            line.append(makeElement("strong", "", comment.username), document.createTextNode(comment.comment));
            commentsBox.append(line);
        });
        postCard.querySelector(".comment-count").textContent =
            `${comments.length} ${comments.length === 1 ? "comment" : "comments"}`;
    } catch (error) {
        commentsBox.replaceChildren(makeElement("p", "comment", error.message));
    }
}

function createPostCard(post) {
    const card = makeElement("article", "post-card card");
    const header = makeElement("div", "post-header");
    const avatar = makeElement("img", "avatar");
    avatar.src = avatarPath(post.profile_picture);
    avatar.alt = `${post.username}'s profile`;
    const authorBlock = makeElement("div");
    authorBlock.append(
        makeElement("div", "post-author", post.username),
        makeElement("div", "post-time", formatDate(post.created_at))
    );
    header.append(avatar, authorBlock);

    const image = makeElement("img", "post-image");
    image.src = avatarPath(post.image);
    image.alt = `Photo shared by ${post.username}`;
    image.loading = "lazy";

    const content = makeElement("div", "post-content");
    const actions = makeElement("div", "post-actions");
    const likeButton = makeElement("button", `like-button${post.liked_by_me ? " liked" : ""}`);
    likeButton.type = "button";
    likeButton.setAttribute("aria-pressed", String(post.liked_by_me));
    const heart = makeElement("span", "heart", post.liked_by_me ? "♥" : "♡");
    heart.setAttribute("aria-hidden", "true");
    const likeCount = makeElement("span", "like-count", `${post.like_count} ${post.like_count === 1 ? "like" : "likes"}`);
    likeButton.append(heart, likeCount);
    const commentCount = makeElement(
        "span",
        "comment-count",
        `${post.comment_count} ${post.comment_count === 1 ? "comment" : "comments"}`
    );
    actions.append(likeButton, commentCount);

    const caption = makeElement("p", "post-caption");
    caption.append(makeElement("strong", "", post.username), document.createTextNode(post.caption));
    const comments = makeElement("div", "comments");
    const form = makeElement("form", "comment-form");
    const input = makeElement("input");
    input.type = "text";
    input.name = "comment";
    input.maxLength = 300;
    input.placeholder = "Add a kind comment…";
    input.setAttribute("aria-label", `Comment on ${post.username}'s post`);
    input.required = true;
    const submit = makeElement("button", "", "Post");
    submit.type = "submit";
    form.append(input, submit);
    content.append(actions, caption, comments, form);
    card.append(header, image, content);

    likeButton.addEventListener("click", async () => {
        likeButton.disabled = true;
        try {
            const result = await apiRequest(`/api/posts/${post.post_id}/like`, {
                method: post.liked_by_me ? "DELETE" : "POST",
            });
            post.liked_by_me = result.liked;
            likeButton.classList.toggle("liked", result.liked);
            likeButton.setAttribute("aria-pressed", String(result.liked));
            heart.textContent = result.liked ? "♥" : "♡";
            likeCount.textContent = `${result.like_count} ${result.like_count === 1 ? "like" : "likes"}`;
        } catch (error) {
            window.alert(error.message);
        } finally {
            likeButton.disabled = false;
        }
    });

    form.addEventListener("submit", async (event) => {
        event.preventDefault();
        submit.disabled = true;
        try {
            await apiRequest(`/api/posts/${post.post_id}/comments`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ comment: input.value }),
            });
            input.value = "";
            await renderComments(card, post);
        } catch (error) {
            window.alert(error.message);
        } finally {
            submit.disabled = false;
        }
    });

    renderComments(card, post);
    return card;
}

async function loadPosts() {
    feedStatus.textContent = "Loading…";
    try {
        const posts = await apiRequest("/api/posts");
        postList.replaceChildren();
        if (posts.length === 0) {
            postList.append(makeElement("div", "empty-state card", "No posts yet. Share the first little moment!"));
        } else {
            posts.forEach((post) => postList.append(createPostCard(post)));
        }
        feedStatus.textContent = `${posts.length} ${posts.length === 1 ? "post" : "posts"}`;
    } catch (error) {
        postList.replaceChildren(makeElement("div", "empty-state card", error.message));
        feedStatus.textContent = "";
    }
}

fileInput.addEventListener("change", () => {
    fileName.textContent = fileInput.files[0]?.name || "PNG, JPG, GIF or WEBP · max 5 MB";
});

postForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    const submit = postForm.querySelector('button[type="submit"]');
    submit.disabled = true;
    setMessage(postMessage, "");
    try {
        await apiRequest("/api/posts", { method: "POST", body: new FormData(postForm) });
        postForm.reset();
        fileName.textContent = "PNG, JPG, GIF or WEBP · max 5 MB";
        setMessage(postMessage, "Your moment was shared!", "success");
        await loadPosts();
    } catch (error) {
        setMessage(postMessage, error.message, "error");
    } finally {
        submit.disabled = false;
    }
});

(async function startApp() {
    try {
        const data = await apiRequest("/api/session");
        currentUser = data.user;
        csrfToken = data.csrf_token;
        signedInName.textContent = currentUser.username;
        profileNav.href = `/profile/${currentUser.user_id}`;
        composerAvatar.src = avatarPath(currentUser.profile_picture);
        composerAvatar.alt = `${currentUser.username}'s profile`;
        await loadPosts();
    } catch (error) {
        feedStatus.textContent = error.message;
    }
})();
