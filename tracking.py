"""Keep the controlling hand selected when a second hand enters the image."""
import math

class HandSelector:
    def __init__(self):
        self.label = None
        self.last_center = None

    def switch(self):
        self.label = {'Left':'Right','Right':'Left'}.get(self.label)
        self.last_center = None

    def select(self, hands, handedness, roi):
        candidates = []
        for i, hand in enumerate(hands):
            if i >= len(handedness) or not handedness[i]:
                continue
            category = handedness[i][0]
            label = category.category_name
            if label not in ('Left','Right') or category.score < .65:
                continue
            centre = ((hand[0].x+hand[9].x)/2, (hand[0].y+hand[9].y)/2)
            candidates.append((i,label,centre))
        if self.label is None:
            # Acquire the hand nearest the middle of the working area, not model order.
            usable = [v for v in candidates if roi[0] <= hands[v[0]][8].x <= roi[2]
                      and roi[1] <= hands[v[0]][8].y <= roi[3]]
            if not usable:
                return None
            cx,cy=(roi[0]+roi[2])/2,(roi[1]+roi[3])/2
            chosen=min(usable,key=lambda v:math.hypot(hands[v[0]][8].x-cx,hands[v[0]][8].y-cy))
            self.label=chosen[1]
        else:
            usable=[v for v in candidates if v[1]==self.label]
            if not usable:
                # Never transfer control to the other hand when the selected one leaves.
                return None
            if len(usable)>1:
                if self.last_center is None:
                    return None
                ranked=sorted(usable,key=lambda v:math.dist(v[2],self.last_center))
                first,second=[math.dist(v[2],self.last_center) for v in ranked[:2]]
                if first>.25 or second-first<.08:
                    return None  # ambiguous/crossing hands: wait rather than jump
                chosen=ranked[0]
            else:
                chosen=usable[0]
        self.last_center=chosen[2]
        return chosen[0]
