"""Bus/device value structures. Resolve references before layout and every export."""

from .i18n import _
from .model import Bus, Device, Flag, MapCan, ValueTable


def effective_structure(bus: Bus, dev: Device | None, name: str) -> tuple[ValueTable, str] | None:
    base = bus.structures.get(name)
    own = dev.structures.get(name) if dev else None
    if base is not None and not base.enabled:
        base = None
    locked = set(base.locked) if base else set()
    if own is not None and not own.enabled and not locked:
        return None
    if base is None and own is None:
        return None
    values = dict(base.values) if base else {}
    if own:
        values = {k: v for k, v in values.items() if k in locked or (own.enabled and k not in own.excluded)}
        if own.enabled:
            values.update({k: v for k, v in own.values.items() if k not in locked and k not in own.excluded})
    return values, base.kind if base else own.kind


def resolve_structures(cmap: MapCan, src, report) -> None:
    for bi, bus in enumerate(cmap.buses):
        owners = [(None, bus.frames, ("buses", bi))]
        owners += [(dev, dev.frames, ("buses", bi, "devices", di)) for di, dev in enumerate(bus.devices)]
        for dev, frames, owner_path in owners:
            def bind(node, path, bus=bus, dev=dev):
                ref = node.values
                if not isinstance(ref, str) or not ref.startswith("structure:"):
                    return
                result = effective_structure(bus, dev, ref[len("structure:"):])
                if result is None:
                    report.add(src.diag("error", "structure", _("Structure {name!r} is not available for this device.",
                                                               name=ref[len("structure:"):]), path + ("values",)))
                    node.values = None
                    return
                values, kind = result
                if kind == "bitmask" and any(k <= 0 or k & (k - 1) for k in values):
                    report.add(src.diag("error", "structure", _("bitmask values must be positive powers of two"),
                                        path + ("values",)))
                    node.values = None
                    return
                # A mask structure becomes bit flags in the resolved layout, so all exporters see the same bits.
                if kind == "bitmask" and hasattr(node, "flags"):
                    node.encoding = "bitfield"
                    node.values = None
                    node.flags = [Flag(name=v if isinstance(v, str) else v.name, bit=k.bit_length() - 1,
                                       description=None if isinstance(v, str) else v.description)
                                  for k, v in sorted(values.items())]
                else:
                    node.values = values
                    if hasattr(node, "encoding"):
                        node.encoding = "enum"

            for fi, frame in enumerate(frames):
                fp = owner_path + ("frames", fi)
                for si, signal in enumerate(frame.signals):
                    sp = fp + ("signals", si)
                    bind(signal, sp)
                    for i, flag in enumerate(signal.flags or []):
                        bind(flag, sp + ("flags", i))
                for ei, exchange in enumerate(frame.sdo or []):
                    if exchange.value is not None:
                        bind(exchange.value, fp + ("sdo", ei, "value"))
