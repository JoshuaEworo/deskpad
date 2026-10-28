# Phone camera and audio setup

Open desktop **Settings → Phone camera & audio**. Each feature has its own setup
status and instructions. Enable the feature, **Save settings**, then turn it on
from the phone's Deskpad menu. Saving a media-permission change reconnects the phone.

| Status | Meaning |
| --- | --- |
| Setup required | A supported Windows device is missing; choose Set up. |
| Ready to enable | Setup was detected; enable the feature and save. |
| Save to enable / Save to turn off | Your checkbox change has not been saved yet. |
| Enabled on laptop | Laptop permission is saved; start it from your phone. |
| Starting / Active | The phone requested it / the media bridge is processing frames. |
| Needs attention | The bridge failed; the message explains the last error. |
| Unavailable | This platform/build cannot provide the feature. |

Setup checks do not capture media or install drivers. Detection is not an
end-to-end Zoom test: start the feature from your phone and check Zoom's preview
or microphone meter to finish verifying it on your equipment.

## Phone as a webcam

The current adapter supports **OBS Virtual Camera** and **Unity Video Capture**.
For the normal setup, install [OBS Studio](https://obsproject.com/download) with
its virtual camera component. Return to Deskpad and choose **Refresh devices**.
Enable **Use phone as a webcam** and save.

Use **Anywhere** mode for the phone's secure link, even on home Wi-Fi. In the
phone's Deskpad menu turn on **Use phone camera** and grant camera permission.
In Zoom on the laptop, select the virtual camera named in Deskpad's instructions.
Leave OBS's **Start Virtual Camera** off: Deskpad supplies the frames directly.

## Phone as a microphone

Install [VB-CABLE from VB-Audio](https://vb-audio.com/Cable/) and follow its restart
instructions. If Deskpad was already open during installation, **Quit from the
system tray** and open it again so its audio library sees the new Windows device.
Closing its window normally just hides it in the tray.

Select the detected virtual cable in Deskpad, enable **Use phone as a microphone**
and save. The selector lists supported VB-CABLE playback endpoints only; ordinary
speakers and duplicate audio-API entries are excluded. An old physical-speaker
selection cannot receive phone microphone samples.

Connect through **Anywhere** mode, turn on **Use phone microphone** from the phone
menu, and grant permission. In Zoom choose **CABLE Output (VB-Audio Virtual Cable)**
as the microphone. For CABLE-A/B, choose the matching Output. The driver calls
Deskpad's playback side Input and Zoom's recording side Output; the in-app guide
keeps these steps together.

## Hear laptop audio on the phone

No additional virtual device is needed. Choose a Windows sound output, enable
**Hear laptop audio on phone**, and save. Then turn on **Hear laptop audio** in the
phone's menu. Browser audio playback starts after your tap. This sends laptop sound
to the phone; it does not select a camera or microphone in Zoom. Use headphones
if playback feeds back into your microphone.

## Current limits

These are adapters for installed Windows devices. Deskpad-branded webcam and
microphone drivers are not bundled yet. Third-party installers run outside Deskpad
and may ask for Windows administrator approval or a restart. Only open the official
pages linked above. The Settings guide and phone's disabled-control explanations
show the next action instead of treating a permission checkbox as a finished setup.
