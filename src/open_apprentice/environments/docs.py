"""PUBLIC tool documentation, identical for every policy (spec 4.2). It describes the DOCUMENTED
contract only; controlled undocumented changes are never reflected here."""

COMMON = (
    "Tools take named arguments and return objects. observe_geometry(node_ids) reports the actual rendered WORLD "
    "bounds {id,left,top,width,height} - use it to verify results. measure_node(node_id) reports the backend's "
    "own measurement (see its `frame` field). move_node(node_id,x,y) places a node; resize_node(node_id,width,height) "
    "resizes; clone_node(node_id,new_id) copies a node (the copy starts at the original's position) and returns the copy."
)

DOCS = {
    "konva": COMMON
    + " Konva: x,y are in the node's parent frame; scenes in this task are flat, so that frame is the canvas.",
    "fabric": COMMON
    + " Fabric: positions are the object's left/top in canvas coordinates; clone_node is asynchronous internally "
    "but returns normally; group_nodes/ungroup_node are unsupported and return UNSUPPORTED_CAPABILITY.",
}
