const profileUserId = Number(document.querySelector(".profile-page").dataset.profileUserId);
const profileDetails = document.querySelector("#profile-details");
const profilePostList = document.querySelector("#post-list");
const profileFeedStatus = document.querySelector("#profile-feed-status");
const signedInName = document.querySelector("#signed-in-name");
let csrfToken;

async function profileApiRequest(url, options = {}) {
    const requestOptions = { ...options, headers: { ...(options.headers || {}) } };
    if (["POST", "PUT", "PATCH", "DELETE"].includes(requestOptions.method)) {
        requestOptions.headers["X-CSRF-Token"] = csrfToken;
    }
    const response = await fetch(url, requestOptions);
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || "Something went wrong. Please try again.");
    return data;
}

function makeProfileElement(tag, className, text) {
    const element = document.createElement(tag);
    if (className) element.className = className;
    if (text !== undefined) element.textContent = text;
    return element;
}

async function loadProfile(sessionUser) {
    const [user, posts] = await Promise.all([
        profileApiRequest(`/api/users/${profileUserId}`),
        profileApiRequest(`/api/users/${profileUserId}/posts`),
    ]);
    document.title = `Little Moments — ${user.username}`;
    const avatar = makeProfileElement("img", "profile-avatar");
    avatar.src = `/media/${encodeURIComponent(user.profile_picture)}`;
    avatar.alt = `${user.username}'s profile`;
    const info = document.createElement("div");
    const eyebrow = makeProfileElement("p", "eyebrow", "LITTLE MOMENTS MEMBER");
    const name = makeProfileElement("h1", "", user.username);
    const subtitle = makeProfileElement("p", "", "Sharing a little bit of everyday life.");
    const count = makeProfileElement(
        "p",
        "profile-count",
        `${user.post_count} ${user.post_count === 1 ? "post" : "posts"}`
    );
    info.append(eyebrow, name, subtitle, count);
    profileDetails.replaceChildren(avatar, info);
    signedInName.textContent = sessionUser.username;
    signedInName.href = `/profile/${sessionUser.user_id}`;
    profilePostList.replaceChildren();
    if (posts.length === 0) {
        profilePostList.append(makeProfileElement("div", "empty-state card", "No posts from this user yet."));
    } else {
        posts.forEach((post) => profilePostList.append(buildProfilePost(post)));
    }
    profileFeedStatus.textContent = `${posts.length} ${posts.length === 1 ? "moment" : "moments"}`;
}

function buildProfilePost(post) {
    const card = makeProfileElement("article", "post-card card");
    const header = makeProfileElement("div", "post-header");
    const avatar = makeProfileElement("img", "avatar");
    avatar.src = `/media/${encodeURIComponent(post.profile_picture)}`;
    avatar.alt = `${post.username}'s profile`;
    header.append(avatar, makeProfileElement("div", "post-author", post.username));
    const image = makeProfileElement("img", "post-image");
    image.src = `/media/${encodeURIComponent(post.image)}`;
    image.alt = `Photo shared by ${post.username}`;
    const content = makeProfileElement("div", "post-content");
    const actions = makeProfileElement("div", "post-actions");
    const likeButton = makeProfileElement("button", `like-button${post.liked_by_me ? " liked" : ""}`);
    likeButton.type = "button";
    likeButton.setAttribute("aria-pressed", String(post.liked_by_me));
    const heart = makeProfileElement("span", "heart", post.liked_by_me ? "♥" : "♡");
    heart.setAttribute("aria-hidden", "true");
    const likeCount = makeProfileElement("span", "like-count", `${post.like_count} ${post.like_count === 1 ? "like" : "likes"}`);
    likeButton.append(heart, likeCount);
    const commentCount = makeProfileElement("span", "comment-count", `${post.comment_count} ${post.comment_count === 1 ? "comment" : "comments"}`);
    actions.append(likeButton, commentCount);
    const caption = makeProfileElement("p", "post-caption");
    caption.append(makeProfileElement("strong", "", post.username), document.createTextNode(post.caption));
    const comments = makeProfileElement("div", "comments");
    const form = makeProfileElement("form", "comment-form");
    const input = makeProfileElement("input");
    input.type = "text";
    input.maxLength = 300;
    input.placeholder = "Add a kind comment…";
    input.setAttribute("aria-label", `Comment on ${post.username}'s post`);
    input.required = true;
    const submit = makeProfileElement("button", "", "Post");
    submit.type = "submit";
    form.append(input, submit);
    content.append(actions, caption, comments, form);
    card.append(header, image, content);

    async function refreshComments() {
        try {
            const results = await profileApiRequest(`/api/posts/${post.post_id}/comments`);
            comments.replaceChildren();
            results.forEach((item) => {
                const line = makeProfileElement("p", "comment");
                line.append(makeProfileElement("strong", "", item.username), document.createTextNode(item.comment));
                comments.append(line);
            });
            commentCount.textContent = `${results.length} ${results.length === 1 ? "comment" : "comments"}`;
        } catch (error) {
            comments.textContent = error.message;
        }
    }

    likeButton.addEventListener("click", async () => {
        likeButton.disabled = true;
        try {
            const result = await profileApiRequest(`/api/posts/${post.post_id}/like`, {
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
            await profileApiRequest(`/api/posts/${post.post_id}/comments`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ comment: input.value }),
            });
            input.value = "";
            await refreshComments();
        } catch (error) {
            window.alert(error.message);
        } finally {
            submit.disabled = false;
        }
    });
    refreshComments();
    return card;
}

(async function startProfile() {
    try {
        const data = await profileApiRequest("/api/session");
        csrfToken = data.csrf_token;
        await loadProfile(data.user);
    } catch (error) {
        profileDetails.textContent = error.message;
        profileFeedStatus.textContent = "";
    }
})();
