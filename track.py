from dataclasses import  dataclass

@dataclass
class Track:
    ttype: str    

    def get_shape(self):        
        return self.unit_price * self.quantity_on_hand