/** 
 * Global utilities file.  You can call these from anythwere!
 */

Atmo.Utils.relative_time = function(date_obj) {
    var seconds = Math.floor((new Date() - date_obj) / 1000);

    var interval = Math.floor(seconds / 31536000);

    if (interval > 1) {
        return interval + " years ago";
    }
    interval = Math.floor(seconds / 2592000);
    if (interval > 1) {
        return interval + " months ago";
    }
    interval = Math.floor(seconds / 86400);
    if (interval > 1) {
        return interval + " days ago";
    }
    interval = Math.floor(seconds / 3600);
    if (interval > 1) {
        return interval + " hours ago";
    }
    interval = Math.floor(seconds / 60);
    if (interval > 1) {
        return interval + " minutes ago";
    }
    return Math.floor(seconds) + " seconds ago";
}

Atmo.Utils.evil_chris_time_parse = function(str_date) {
  if(str_date && (typeof str_date == 'object') && str_date.length > 19) {
    return Date.parse(str_date.substring(0,19)).setTimezoneOffset(0);
  }  
}

Atmo.Utils.hide_all_help = function() {
    $('[id^=help_]').popover('hide');
};

Atmo.Utils.update_weather = function() {
/*    getAtmoMethod("getOccupancy", null, true, function(occupancy) {

        var weather_classes = ['sunny', 'cloudy', 'rainy', 'stormy'];
        var weather = '';

        if(occupancy > 85)
            weather = weather_classes[3]
        else if(occupancy > 60)
            weather = weather_classes[2]
        else if(occupancy > 35)
            weather = weather_classes[1]
        else if(occupancy >= 0)
            weather = weather_classes[0]

        if (!$('#weather_report').hasClass(weather)) {
            $.each(weather_classes, function(k, v) {
                $('body').removeClass(v);
            });
            $('#weather_report').addClass(weather);
            //Atmo.Utils.notify("Weather Report", "Atmosphere is at " + occupancy + "% capacity. The forecast is " + weather + ".");
            $('#weather_report').html('Atmosphere is at ' + occupancy + '% capacity.<br /> The forecast is '+weather+'.');
        }

    }, function() {
            // Default weather?    
    });
*/
};

Atmo.Utils.confirm = function(header, body, options) {
    Atmo.alert_modal.do_alert(header, body, options);
};

Atmo.Utils.notify = function(header, body, options) {
    var defaults = {no_timeout: false};
    var options = options ? _.defaults(options, defaults) : defaults;
    Atmo.notifications.add({'header': header, 'body': body, 'timestamp': new Date(), 'sticky': options.no_timeout });
};

// case-insensitive Levenshtein Distance as defined by http://en.wikipedia.org/wiki/Levenshtein_distance
Atmo.Utils.levenshtein_distance= function(s, t) {
    var len_s = s.length, len_t = t.length, cost = 0;
    s = s.toLowerCase();
    t = t.toLowerCase();

    if (s[0] != t[0])
        cost = 1;

    if (len_s == 0)
        return len_t;
    else if (len_t == 0)
        return len_s;
    else
        return Math.min(
            Atmo.Utils.levenshtein_distance(s.substr(1), t) + 1, 
            Atmo.Utils.levenshtein_distance(s, t.substr(1)) + 1, 
            Atmo.Utils.levenshtein_distance(s.substr(1), t.substr(1)) + cost
        );
}

Atmo.Utils.get_profile = function() {
  profile = new Atmo.Models.Profile();
  var model_name = profile.get('model_name');
  var params = {};
  console.log(params);
  console.log(model_name);
  var url = profile.get('api_url')
    + "/" + model_name;
  console.log(url);
  $.ajax({
    type: "GET",
    contentType:"application/json; charset=utf-8",
    dataType:"json",
    url: url,
    data: params,
    success: function(data, textStatus, jqXHR) {
      console.log(data);
      console.log(textStatus);
      console.log(jqXHR);
      $.each(data, function(key, value) {
        profile.set(key, value);
      });
      console.log("processing in Atmo.Utils.get_profile.success");
      //options.success(profile);
    },
    error: function(data, textStatus, jqXHR) {
      console.log(data);
      console.log(textStatus);
      console.log(jqXHR);
      console.log("processing in Atmo.Utils.get_profile.success");
      //options.error('failed to ' + method
      //              + model_name
      //              + "="
      //              + id);
    },
  });
  return profile;
}

// deprecated.   Use Atmo.profile.get('selected_identity')
Atmo.Utils.current_credentials = function() {
  //console.log("current_credentials");
  return { "provider_id": Atmo.profile.get('selected_identity').get('provider_id'),
           "identity_id": Atmo.profile.get('selected_identity').id
         };
}
Atmo.Utils.attach_volume = function(volume, instance, options) {
    var options = options || {};
    console.log("instance to attach to", instance);

    volume.attach_to(instance, {
        success: function(response_text) {
            var header = "Volume Successfully Attached";
            var body = 'You must <a href="https://pods.iplantcollaborative.org/wiki/x/OKxm#AttachinganEBSVolumetoanInstance-Step6%3AMountthefilesystemonthepartition." target="_blank">mount the volume</a> you before you can use it.<br />';
            body += 'If the volume is new, you will need to <a href="https://pods.iplantcollaborative.org/wiki/x/OKxm#AttachinganEBSVolumetoanInstance-Step5%3ACreatethefilesystem%28onetimeonly%29." target="_blank">create the file system</a> first.';

			console.log("success response text", response_text);

            Atmo.Utils.notify(header, body, { no_timeout: true });
            if (options.success)
                options.success();
        },
        error: function() {
            var header = "Volume attachment failed.";
            var body = "If this problem persists, contact support at <a href=\"mailto:support@iplantcollaborative.org\">support@iplantcollaborative.org</a>"
            Atmo.Utils.notify(header, body, { no_timeout: true});
        }
    });
};

Atmo.Utils.confirm_detach_volume = function(volume, instance, options) {
    var header = "Do you want to detach <strong>"+volume.get('name_or_id')+'</strong>?';
    var body = '<p class="alert alert-error"><i class="icon-warning-sign"></i> <strong>WARNING</strong> If this volume is mounted, you <u>must</u> unmount it before detaching it.</p>'; 
    body += '<p>If you detach a mounted volume, you run the risk of corrupting your data and the volume itself. (<a href="https://pods.iplantcollaborative.org/wiki/x/OKxm#AttachinganEBSVolumetoanInstance-Step7%3AUnmountanddetachthevolume." target="_blank">Learn more about unmounting and detaching a volume</a>)</p>';

    Atmo.Utils.confirm(header, body, { 
        on_confirm: function() {
            Atmo.Utils.notify("<img src=\""+site_root +"/resources/images/loader_bluebg.gif\" /> Detaching volume.", "", {no_timeout: true});
            volume.detach(instance, {
                success: function() {
                    Atmo.Utils.notify("Volume Detached", "Volume is now available to attach to another instance or to destroy.");
                },
                error: function() {
                    Atmo.Utils.notify("Volume failed to detach", "If the problem persists, please email <a href=\"mailto:support@iplantcollaborative.org\">support@iplantcollaborative.org</a>.", {no_timeout: true});
                }
            }); 
        },
        on_cancel: function() {
            console.log("cancelled volume detach.");
            Atmo.volumes.fetch();
        },
        ok_button: 'Yes, detach this volume'
    });
};

