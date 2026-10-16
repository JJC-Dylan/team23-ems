/* ==========================================================================
   Employee Management System - browser behaviour
   The interface works without JavaScript; this file only adds a confirmation
   step in front of destructive actions and a couple of small conveniences.
   ========================================================================== */
(function () {
  "use strict";

  /* --- destructive-action confirmation (URS Use Case 5 step 1) ---------- */
  var modal = null;
  var modalText = null;
  var pendingForm = null;

  function buildModal() {
    if (modal) {
      return modal;
    }
    modal = document.createElement("div");
    modal.className = "modal";
    modal.hidden = true;
    modal.setAttribute("role", "dialog");
    modal.setAttribute("aria-modal", "true");

    var box = document.createElement("div");
    box.className = "modal__box";

    var heading = document.createElement("h2");
    heading.textContent = "Please confirm";

    modalText = document.createElement("p");
    modalText.className = "muted";

    var actions = document.createElement("div");
    actions.className = "modal__actions";

    var cancel = document.createElement("button");
    cancel.type = "button";
    cancel.className = "button button--ghost";
    cancel.textContent = "Cancel";
    cancel.addEventListener("click", closeModal);

    var confirm = document.createElement("button");
    confirm.type = "button";
    confirm.className = "button button--danger";
    confirm.textContent = "Confirm delete";
    confirm.addEventListener("click", function () {
      if (pendingForm) {
        var form = pendingForm;
        pendingForm = null;
        form.dataset.confirmed = "yes";
        form.submit();
      }
      closeModal();
    });

    actions.appendChild(cancel);
    actions.appendChild(confirm);
    box.appendChild(heading);
    box.appendChild(modalText);
    box.appendChild(actions);
    modal.appendChild(box);
    document.body.appendChild(modal);

    modal.addEventListener("click", function (event) {
      if (event.target === modal) {
        closeModal();
      }
    });
    document.addEventListener("keydown", function (event) {
      if (event.key === "Escape" && !modal.hidden) {
        closeModal();
      }
    });
    return modal;
  }

  function openModal(message, form) {
    buildModal();
    modalText.textContent = message;
    pendingForm = form;
    modal.hidden = false;
  }

  function closeModal() {
    if (modal) {
      modal.hidden = true;
    }
    pendingForm = null;
  }

  document.addEventListener("submit", function (event) {
    var form = event.target;
    if (!form || !form.dataset || !form.dataset.confirm) {
      return;
    }
    if (form.dataset.confirmed === "yes") {
      return;
    }
    event.preventDefault();
    openModal(form.dataset.confirm, form);
  });

  /* --- filter bar: keep the query string short and readable ------------- */
  document.addEventListener("DOMContentLoaded", function () {
    var filterForms = document.querySelectorAll("form.filter-bar");
    Array.prototype.forEach.call(filterForms, function (form) {
      form.addEventListener("submit", function () {
        Array.prototype.forEach.call(
          form.querySelectorAll("input, select"),
          function (field) {
            if (!field.name || field.value !== "") {
              return;
            }
            // Disabled fields are not submitted, which keeps the address tidy.
            field.disabled = true;
            window.setTimeout(function () {
              field.disabled = false;
            }, 0);
          }
        );
      });
    });

    // Focus the search box when an overview page opens.
    var search = document.getElementById("q");
    if (search && !search.value) {
      search.focus({ preventScroll: true });
    }
  });
})();
