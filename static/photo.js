"use strict";

// RNG-6: photo upload -> /classify-ring -> pre-fill the ring form.
// Plain script (no modules), operates by id. Never touches inner_diameter.
(function () {
  var MAX_EDGE = 1024;
  var ESTIMABLE = [
    "band_width",
    "band_thickness",
    "stone_diameter",
    "stone_height",
    "setting_height",
  ];

  function $(id) {
    return document.getElementById(id);
  }

  function setStatus(msg) {
    var el = $("photo-status");
    if (el) {
      el.textContent = msg;
    }
  }

  function downscale(file) {
    return new Promise(function (resolve, reject) {
      var url = URL.createObjectURL(file);
      var img = new Image();
      img.onload = function () {
        URL.revokeObjectURL(url);
        var w = img.naturalWidth;
        var h = img.naturalHeight;
        var longest = Math.max(w, h);
        var scale = longest > MAX_EDGE ? MAX_EDGE / longest : 1;
        var cw = Math.max(1, Math.round(w * scale));
        var ch = Math.max(1, Math.round(h * scale));
        var canvas = document.createElement("canvas");
        canvas.width = cw;
        canvas.height = ch;
        var ctx = canvas.getContext("2d");
        ctx.drawImage(img, 0, 0, cw, ch);
        canvas.toBlob(
          function (blob) {
            if (blob) {
              resolve(blob);
            } else {
              reject(new Error("toBlob failed"));
            }
          },
          "image/jpeg",
          0.9
        );
      };
      img.onerror = function () {
        URL.revokeObjectURL(url);
        reject(new Error("image load failed"));
      };
      img.src = url;
    });
  }

  function applyEstimates(estimates) {
    ESTIMABLE.forEach(function (key) {
      var val = estimates[key];
      var input = $(key);
      if (input && typeof val === "number") {
        input.value = String(val);
      }
    });
    if (typeof estimates.prong_count === "number") {
      var select = $("prong_count");
      if (select) {
        select.value = String(estimates.prong_count);
      }
    }
  }

  function showDetections(data) {
    var el = $("photo-detections");
    if (!el) {
      return;
    }
    var parts = [];
    if (data.style) {
      parts.push(data.style);
    }
    if (data.shank_taper) {
      parts.push(data.shank_taper + " shank");
    }
    var text = "Detected: " + (parts.length ? parts.join(", ") : "ring");
    if (data.features && data.features.length) {
      text += " (" + data.features.join(", ") + ")";
    }
    el.textContent = text;
    el.hidden = false;
  }

  function handleSuccess(data) {
    if (data && data.ring_detected) {
      applyEstimates(data.estimates || {});
      var label = $("estimates-label");
      if (label) {
        label.hidden = false;
      }
      showDetections(data);
      setStatus(data.note || "Estimates applied. Verify before generating.");
    } else {
      setStatus(
        (data && data.note) ||
          "No ring detected — enter parameters manually."
      );
    }
  }

  function errorMessage(status, data) {
    if (status === 503) {
      return "Photo classification isn't configured. Enter parameters manually below.";
    }
    if (data && (data.detail || data.error)) {
      return data.detail || data.error;
    }
    return "Could not analyse the photo, try again.";
  }

  function onEstimate() {
    var fileInput = $("ring-photo");
    var file = fileInput && fileInput.files ? fileInput.files[0] : null;
    if (!file) {
      setStatus("Choose a JPEG or PNG photo first.");
      return;
    }
    var btn = $("estimate-btn");
    if (btn) {
      btn.disabled = true;
    }
    setStatus("Analysing photo…");

    downscale(file)
      .then(function (blob) {
        var form = new FormData();
        form.append("image", blob, "ring.jpg");
        return fetch("/classify-ring", { method: "POST", body: form });
      })
      .then(function (resp) {
        return resp
          .json()
          .catch(function () {
            return {};
          })
          .then(function (data) {
            if (resp.ok) {
              handleSuccess(data);
            } else {
              setStatus(errorMessage(resp.status, data));
            }
          });
      })
      .catch(function () {
        setStatus("Could not reach the server, try again.");
      })
      .then(function () {
        if (btn) {
          btn.disabled = false;
        }
      });
  }

  document.addEventListener("DOMContentLoaded", function () {
    var btn = $("estimate-btn");
    if (btn) {
      btn.addEventListener("click", onEstimate);
    }
  });
})();
