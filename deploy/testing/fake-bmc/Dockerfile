# Runs sushy-tools' Redfish emulator in --fake mode -- no libvirt, no
# KVM, no nested virtualization needed at all, because it doesn't back
# onto any real VM. It just simulates N BMCs entirely in memory/state
# file, which is enough for Ironic (or this project's backend, or your
# own testing) to exercise the exact same Redfish power/boot-override
# protocol it would use against real hardware. Runs fine on any cloud VM
# regardless of whether nested virtualization is available.
FROM python:3.12-slim

RUN pip install --no-cache-dir sushy-tools==1.4.0

COPY sushy-fake.conf /etc/sushy/sushy-fake.conf

EXPOSE 8000
CMD ["sushy-emulator", "--fake", "--config", "/etc/sushy/sushy-fake.conf"]
