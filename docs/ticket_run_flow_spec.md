GM: specification + QA, basically client's double stunt
OM: CTO+COO
Engineer: Engineers



Ticket:
current ticket:

CREATE TABLE tickets (
id UUID PRIMARY KEY DEFAULT gen_random_uuid () ,
project_id UUID REFERENCES projects ( id ) ON DELETE CASCADE ,
from_agent UUID REFERENCES agents ( id ) ON DELETE CASCADE ,
to_agent UUID REFERENCES agents ( id ) ON DELETE CASCADE ,
header VARCHAR (255) NOT NULL ,
ticket_type VARCHAR (50) NOT NULL ,
-- ' task_assignment ' , ' question ' , ' help ' , ' issue '
critical INT DEFAULT 8 ,
urgent INT DEFAULT 8 ,
status VARCHAR (20) DEFAULT ' open ' , -- ' open ' , ' closed '
created_at TIMESTAMPTZ DEFAULT NOW () ,
closed_at TIMESTAMPTZ ,
closed_by UUID REFERENCES agents ( id )
) ;
